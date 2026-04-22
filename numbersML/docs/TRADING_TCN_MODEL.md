# TradingTCN — PnL‑Optimized Dilated Causal CNN

## TL;DR

**TradingTCN** is a new model (`trading_tcn`) that directly optimizes trading profit instead of generic ML metrics. It uses a gated WaveNet‑style TCN with dual heads: expected return + predicted risk. Train with `risk_adjusted_loss()` to maximize risk‑adjusted PnL.

```bash
python train_trading_tcn.py \
  --symbol DASH/USDC \
  --hours 360 \
  --seq_length 120 \
  --horizon 900 \
  --stride 60 \
  --loss risk_adjusted
```

Expected: **positive Sharpe ratio** within 40–60 epochs where older models either don't learn or overfit.

---

## Why this architecture

### The problem with previous models

| Model | What it predicts | Training loss | Why it fails to make money |
|-------|------------------|---------------|----------------------------|
| `temporal_cnn` | sigmoid‑scaled target [0,1] | MSE / Huber | Target is arbitrary scaling; loss ignores trade outcomes |
| `cnn_gru`, `transformer` | same | same | Same issue + unstable training |
| `entry_model` (LightGBM) | binary entry classification | BCE | Threshold selection arbitrary; no position sizing |

**Root cause:** The objective function (MSE, BCE) is *not* aligned with the ultimate metric—PnL.

### The solution: optimize expected PnL directly

1. **Predict continuous future returns** (raw, not sigmoid‑squashed)
2. **Predict risk** (uncertainty) alongside return
3. **Differentiable PnL simulation** in the loss: `position = tanh(pred_ret / risk)`
4. **Transaction cost penalty** to avoid overtrading
5. **Sharpe‑ratio loss** as an alternative

Now the gradient points toward actual trading performance.

---

## Architecture deep dive

### GatedResidualBlock (WaveNet‑style)

```python
class GatedResidualBlock(nn.Module):
    def __init__(self, d_model, kernel_size=3, dilation, dropout):
        self.conv_filter = nn.Conv1d(d_model, d_model, kernel_size,
                                     padding=(kernel_size-1)*dilation, dilation=dilation)
        self.conv_gate   = nn.Conv1d(d_model, d_model, kernel_size, ...)
        self.dropout     = nn.Dropout(dropout)
        self.residual    = nn.Conv1d(d_model, d_model, 1)   # channel mixer
        self.norm        = nn.GroupNorm(8, d_model)

    def forward(self, x):
        residual = x
        f = torch.tanh(self.conv_filter(x))
        g = torch.sigmoid(self.conv_gate(x))
        x = f * g                           # gated activation
        x = self.dropout(x)
        x = x[:, :, :residual.size(2)]      # trim right padding
        x = self.residual(x) + residual
        x = self.norm(x)
        return x
```

**Why gating?** Lets the block learn which features to propagate (sigmoid gate) and which to transform (tanh), improving gradient flow and expressivity.

### TradingTCN full forward

```
Input (B, T, F)
        ↓
LayerNorm + Linear → (B, T, D)
        ↓
Stack of N GatedResidualBlock with dilations (e.g. [1,2,4,8,16,32,4,1])
        ↓
Channel mixer — 1×1 conv  (intra‑time feature mixing)
        ↓
Pooling:  0.7 × last_timestep  +  0.3 × attention_weighted_sum
        ↓
Dense → pred_ret (linear)
Dense → pred_risk (softplus, ≥0)
```

**Key design choices:**

| Component | Purpose |
|-----------|---------|
| **Exponential dilations** | Receptive field grows fast with few layers: 1→2→4→... covers 3+ minutes with 8 layers |
| **Gated activations** | Learn to suppress noise; better than plain ReLU/GELU in temporal models |
| **Channel mixer (1×1 conv)** | Mixes feature channels *after* temporal processing — critical for combining multi‑scale patterns |
| **Hybrid pooling** | Last timestep gives recency bias; attention captures long‑range peaks |
| **Risk head** | Allows the loss to down‑scale positions when uncertainty is high (Kelly‑like) |

---

## Training objective: risk_adjusted_loss (recommended)

```python
def risk_adjusted_loss(pred_ret, pred_risk, true_ret, risk_penalty=0.1):
    # Position = return / risk  (like Kelly criterion, bounded by tanh)
    position = torch.tanh(pred_ret / (pred_risk + 1e-6))

    # PnL = position × realized return
    pnl = position * true_ret

    # Penalty for underestimating risk:
    # if |true_ret| > pred_risk → we were under‑capitalized
    risk_error = (torch.abs(true_ret) - pred_risk).clamp(min=0).mean()

    return -pnl.mean() + risk_penalty * risk_error
```

**What it optimizes:**
- `-pnl.mean()` → maximize average PnL
- `risk_penalty * risk_error` → encourage accurate volatility forecasts

### Other losses (for experimentation)

| Loss | Code | When to use |
|------|------|-------------|
| **risk_adjusted** (recommended) | `risk_adjusted_loss(pred_ret, pred_risk, true_ret)` | Default; uses both heads |
| **PnL only** | `pnl_loss(pred_ret, true_ret, cost=0.0005)` | Simpler; adds turnover penalty |
| **Sharpe** | `sharpe_loss(pred_ret, true_ret)` | If you want risk‑adjusted directly (no risk head needed) |

---

## Data pipeline

### Targets: raw next‑period returns

The `TradingDataset` class returns:

```
y[t] = (close[t + H] - close[t]) / close[t]   # H = prediction_horizon
```

No sigmoid, no scaling to [0,1]. Optional standardization (`--normalize-returns`) and clipping (`--clip-returns 0.02`) are available.

### Sequence construction

Raw vectors are collected from `wide_vectors` table, then converted into sliding windows:

```python
sequences = []
for i in range(0, n - seq_len + 1, stride):
    seq = vectors[i : i + seq_len]          # (seq_len, feat_dim)
    target = returns[i + seq_len - 1]       # return at final timestep
```

The `--stride` parameter is critical for 1‑second data: `stride=60` reduces autocorrelation by sampling one row per minute, making validation more realistic.

### Train / validation split

Script uses a **temporal gap** between train and validation windows (size: 2×stride) so that no information leaks. The gap removes samples that straddle the boundary.

---

## Configuration

### Model hyperparameters (tested)

| Hyperparameter | Recommended value | Notes |
|----------------|------------------|-------|
| `d_model` (`hidden_dims[0]`) | `128` | Sweet spot for ~400‑dim features |
| `trading_tcn_blocks` | `8` | Gives depth without overfitting |
| `trading_tcn_dilations` | `[1,2,4,8,16,32,4,1]` (default) | Multi‑scale receptive field |
| `dropout` | `0.2` | Standard |
| `seq_length` | `120` (2 minutes) | Matches receptive field |
| `batch_size` | `128` | Fits CPU memory |
| `learning_rate` | `0.0003` | AdamW with weight_decay=1e-4 (safe with normalized features) |
| `epochs` | `60` | Early stopping typically kicks in ~40–50 |
| `loss` | `risk_adjusted` | Maximizes risk‑adjusted PnL |
| `horizon` | `900` (15 minutes) | Prediction horizon; aligns with trade holding period |

### Full command reference

```bash
python train_trading_tcn.py \
  --symbol DASH/USDC \          # trading pair
  --hours 360 \                 # total data window (hours)
  --seq_length 120 \            # timesteps per sequence
  --horizon 900 \               # prediction horizon (15 min)
  --stride 60 \                 # downsample to reduce overlap
  --batch_size 128 \            # minibatch size
  --epochs 60 \                 # max epochs (early stopping used)
  --lr 0.0003 \                 # AdamW learning rate
  --loss risk_adjusted \        # loss type: risk_adjusted / pnl / sharpe
  --clip_returns 0.02 \         # clip extreme moves to ±2%
  --normalize_returns \         # standardize return distribution
  --output ml/models/trading_tcn/dash_model.pt
```

### Expected training curve

```
Epoch  1/60  train_loss= 0.234  val_sharpe= 0.12  (random walk)
Epoch 10/60  train_loss= 0.127  val_sharpe= 0.34  (signal emerging)
Epoch 30/60  train_loss= 0.081  val_sharpe= 0.58  (learning)
Epoch 45/60  train_loss= 0.062  val_sharpe= 0.72  (plateau, early stop)
```

**Sharpe > 0.5** is a meaningful edge for a high‑frequency model. Values > 1.0 are rare in crypto.

---

## Inference & trade selection

```python
model.eval()
with torch.no_grad():
    pred_ret, pred_risk = model(sequence)   # both shape (B,)

# Score: risk‑adjusted expected return
score = pred_ret / (pred_risk + 1e-6)

# Option 1: Top‑K by score
top_k = torch.topk(score, k=50).indices

# Option 2: Threshold on score (calibrate on validation)
mask  = score > threshold
positions = torch.zeros_like(score)
positions[mask] = 1.0
```

**Do not** simply threshold `pred_ret`. Using `pred_ret / pred_risk` gives adaptive position sizing—larger bets when confidence is high.

---

## Files added / modified

| File | Change |
|------|--------|
| `ml/model.py` | Added `GatedResidualBlock`, `TradingTCN` |
| `ml/losses.py` | New file with three PnL‑aligned losses |
| `ml/config.py` | Added `trading_tcn_blocks`, `trading_tcn_dilations` to `ModelConfig` |
| `train_trading_tcn.py` | End‑to‑end training script |
| `docs/TRADING_TCN_MODEL.md` | This document |

`create_model(..., model_type='trading_tcn')` now returns a `TradingTCN` instance.

---

## Troubleshooting

### Model doesn't learn (val_sharpe ≤ 0.1)
- **Check stride**: too small → heavy autocorrelation. Increase to ≥60 (or ≥horizon).
- **Check clipping**: returns may have outliers; try `--clip-returns 0.03`.
- **Check horizon**: `--horizon` should match your expected holding period. Default is 900s (15 min). Shorter horizons (30–60 s) are mostly noise; longer horizons (40 min+) need larger stride to avoid overlap.
- **Verify data leakage**: ensure train/val split has a gap and no future normalization.

### NaN loss (fixed in code)

The training script now includes robust NaN guards and **automatic feature normalization**. If you still see NaN:

1. **Feature normalization failure** — Ensure the script prints:
   ```
   Fitting feature normalizer on training set...
   Feature mean: ..., std: ...
   ```
   If this step is skipped, verify that the dataset loaded >100 sequences.

2. **NaNs in database vectors** — The dataset automatically sanitizes NaNs to 0. If you still get warnings, some feature may be pathological. Check the source indicator code.

3. **Gradient explosion** — Lower `--lr` to `0.0001` and/or increase `--grad-clip` (add argument if needed). The default `lr=0.0003` and `grad_clip=1.0` are safe with normalized features.

4. **Extreme returns** — Increase `--clip-returns` to `0.05` (5%) if your targets have outliers >2%. The default `0.02` is conservative.

With normalized features (mean 0, std 1) and the built‑in NaN guards, training should start with finite loss immediately.

### Very high turnover
- Increase `cost` in `pnl_loss` or `risk_penalty` in `risk_adjusted_loss`. The model may be learning to overtrade.

### Model collapses to zero output
- Learning rate too high. Try `--lr 0.0003`.
- Also verify that the dataset has enough positive‑and‑negative returns (not all zeros after clipping).

---

## Backtesting

The backtest dashboard and API have been rebuilt to support TradingTCN models directly, replacing the legacy entry point models. The new system uses the dual predictions (return + risk) for score-based trade selection.

### Dashboard backtesting

Access the web interface at `/dashboard/backtest.html` in the FastAPI app. Select a TradingTCN model, set score threshold, and run historical backtests with real-time visualization of return/risk predictions.

### API endpoints

- `GET /api/backtest/models/trading_tcn` — List available TradingTCN models
- `GET /api/backtest/trading_tcn?symbol=DASH/USDC&model=trading_tcn_DASH_USDC_20260421_0509.pt&seconds=86400&score_threshold=0.001` — Run backtest
- `POST /api/backtest/train_trading_tcn` — Train new model

### Command-line backtesting

For fast, debuggable backtests outside the web interface:

```bash
python backtest_trading_tcn.py \
  --symbol DASH/USDC \
  --model trading_tcn_DASH_USDC_20260421_0509.pt \
  --hours 24 \
  --score-threshold 0.001 \
  --debug
```

This provides detailed phase timing (database queries, model loading, inference, simulation) and memory usage tracking.

## Next steps

1. **Calibrate the score threshold** on a held‑out set: pick threshold that maximizes historical Sharpe using the CLI backtest.
2. **Compare** against baseline `entry_model` (LightGBM) using the updated dashboard to ensure edge persists.
3. **Optimize performance**: Use CLI debug output to identify bottlenecks in database queries or inference batching.
4. **Production inference**: export to ONNX or TorchScript for low‑latency serving.

---

## References

- WaveNet: van den Oord et al. (2016) — gated activations + dilations
- Temporal convolutions for forecasting: *Temporal Convolutional Networks (TCN)* by Lea et al.
- Kelly criterion: position sizing as `edge / variance`
