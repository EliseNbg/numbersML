# ML Model Architecture Redesign - Complete

## Overview
Complete redesign of the ML prediction model based on quantitative finance best practices. This addresses critical issues like data leakage, improper target construction, and suboptimal architecture choices.

## 🚨 Critical Issues Fixed

### 1. **Data Leakage in Target Calculation** (FIXED)

**BEFORE (WRONG):**
```python
# This uses FUTURE data - model cheats!
smoothed[t] = Hanning(close[t-150 : t+150])
```

**AFTER (CORRECT - Causal Filter):**
```python
# Only uses PAST data - no cheating!
smoothed[t] = Hanning(close[t-300 : t])
```

**Implementation:** `ml/target_builder.py`
- `causal_hanning_filter()`: Implements proper causal convolution
- `compute_target_with_horizon()`: Creates targets with future prediction

### 2. **Target is Not Current Time** (FIXED)

**BEFORE (WRONG):**
```python
# Model just learns to rebuild the filter
target[t] = smoothed_price[t]
```

**AFTER (CORRECT - Future Prediction):**
```python
# Model learns to PREDICT the future!
target[t] = smoothed_price[t + prediction_horizon]
```

**Default:** `prediction_horizon = 30` seconds

### 3. **Architecture Optimized for CPU** (FIXED)

**BEFORE:**
- Transformer with 1000 timesteps = very slow on CPU
- Pure MLP with no temporal understanding

**AFTER:**
- CNN + GRU architecture (recommended for financial time series)
- Fast on CPU, handles 1000+ timesteps easily
- CNN: Extracts local patterns (candlestick patterns, indicator crossovers)
- GRU: Captures temporal dependencies

## 📊 New Architecture

### CNN + GRU Model (RECOMMENDED)

```
Input (1000 × features)
        ↓
1D Convolution (32 channels, kernel=5)
        ↓
1D Convolution (64 channels, kernel=5)
        ↓
Max Pooling (kernel=2)
        ↓
GRU (hidden=128, layers=2)
        ↓
Linear (128 → 64)
        ↓
Linear (64 → 1) - Regression Output
```

### Layer Purposes

| Layer | Purpose | Why It Works |
|-------|---------|--------------|
| CNN 1 | Local pattern detection | Finds micro-structure patterns, candlestick formations |
| CNN 2 | Higher-level features | Detects indicator crossovers, trend changes |
| Pooling | Dimensionality reduction | Reduces computation, prevents overfitting |
| GRU | Temporal dependencies | Learns how patterns evolve over time |
| MLP | Regression | Maps learned features to target value |

## 🔧 Configuration Changes

### New Parameters in `ml/config.py`

```python
# DataConfig additions
hanning_window: int = 300          # Causal filter window size
prediction_horizon: int = 30       # Predict t + 30 seconds
use_indicators: bool = True        # Include technical indicators
use_log_prices: bool = True        # Use log(prices) for stability

# ModelConfig additions
model_arch: str = "cnn_gru"        # New recommended architecture
gru_hidden_dim: int = 128          # GRU hidden size
gru_num_layers: int = 2            # Number of GRU layers
gru_dropout: float = 0.2           # Dropout between GRU layers
cnn_channels: List[int] = [32, 64] # CNN channel sizes
cnn_kernel_size: int = 5           # Convolution kernel size
cnn_pool_size: int = 2             # Pooling size
```

## 📈 Feature Normalization

### Proper Feature Transformation

| Feature Type | Transformation | Reason |
|--------------|---------------|--------|
| Prices | `log(price)` | Stabilizes variance, handles exponential growth |
| Volume | `log(volume + 1)` | Handles large range, zeros allowed |
| Indicators | `StandardScaler` | Zero mean, unit variance |
| Returns | No change | Already normalized |
| Sentiment | Clamp to `[-1, 1]` | Bounded range |

**Global Normalization:**
```python
x = (x - mean) / std
```

## 🎯 Prediction Horizons

The model can predict different time horizons:

| Horizon | Use Case | Difficulty |
|---------|----------|------------|
| 10s | Very short-term scalping | Easy |
| 30s | Short-term trading | Medium |
| 60s | 1-minute prediction | Medium-Hard |
| 300s | 5-minute trend | Hard |

**Recommendation:** Start with 30s, then experiment with different horizons.

## 🧪 Testing Protocol

### Experiment 1: Overfit Test
```bash
# Train on small dataset, many epochs
python3 -m ml.train --model cnn_gru --train-hours 1 --epochs 200 --seq-length 100 --symbol T01/USDC
```

**Expected:** Model should overfit (train loss → 0, val loss increases)
- If NOT: Pipeline has issues

### Experiment 2: Different Horizons
```python
# Test different prediction horizons
for horizon in [10, 30, 60, 300]:
    config.data.prediction_horizon = horizon
    # Train and compare
```

### Experiment 3: Target Types
```python
# Option 1: Predict future smoothed price
target = smoothed_price[t + horizon]

# Option 2: Predict future return
target = (price[t + horizon] - price[t]) / price[t]
```

## 📝 Usage Examples

### Train CNN+GRU Model (Default)
```bash
python3 -m ml.train --model cnn_gru --train-hours 24 --epochs 100 --seq-length 1000 --symbol T01/USDC
```

### Train with Custom Prediction Horizon
```bash
# Edit ml/config.py or pass via code
config.data.prediction_horizon = 60  # Predict 60s into future
```

### Quick Overfit Test
```bash
python3 -m ml.train --model cnn_gru --train-hours 1 --epochs 50 --seq-length 100 --lr 0.01 --symbol T01/USDC
```

### Compare All Architectures
```bash
# Train all models
python3 train_all_models.py

# Compare predictions
python3 -m ml.compare --models \
    ml/models/simple/simple_42_T01USDC_20260403.pt \
    ml/models/cnn_gru/cnn_gru_42_T01USDC_20260403.pt
```

## 🔍 File Structure

```
ml/
├── config.py              # Updated with new parameters
├── model.py               # Added CNN_GRUModel class
├── target_builder.py      # NEW: Causal Hanning filter + prediction horizon
├── dataset.py             # TODO: Update to use target_builder
├── train.py               # Updated to support cnn_gru model type
├── predict.py             # TODO: Update to use new target calculation
└── __init__.py            # Updated exports
```

## ⚠️ Important Notes

### Window Alignment
The most critical part is aligning:
1. **Input window**: `t - sequence_length ... t`
2. **Target window**: `smoothed_price[t + prediction_horizon]`
3. **Hanning window**: `close[t - hanning_window ... t]` (CAUSAL!)

**Example:**
- `sequence_length = 1000` (input: past 1000 seconds)
- `hanning_window = 300` (smooth using past 300 seconds)
- `prediction_horizon = 30` (predict 30 seconds into future)

At time `t`:
- Input: prices from `t-999` to `t`
- Target: smoothed price at `t+30` (computed from prices `t-269` to `t+30`)

### Data Leakage Check
✅ **CORRECT:** Target at time `t` only uses data up to time `t+horizon`
❌ **WRONG:** Target at time `t` uses data beyond `t+horizon`

### MSE Loss Function
MSE tends to force model to predict the mean. This is expected behavior.
- If predictions look too smooth: This is correct! The target IS smooth.
- If you want sharp predictions: Use MAE or Huber loss instead.

## 🚀 Next Steps

1. ✅ Causal Hanning filter implemented
2. ✅ Prediction horizon support added
3. ✅ CNN+GRU architecture implemented
4. ✅ Configuration updated
5. ⏳ Update dataset.py to use target_builder
6. ⏳ Add proper feature normalization (log prices, StandardScaler)
7. ⏳ Test with real data
8. ⏳ Compare with old architecture

## 📚 References

- Causal Convolutions: "WaveNet: A Generative Model for Raw Audio" (van den Oord et al., 2016)
- GRU: "Learning Phrase Representations using RNN Encoder-Decoder for Statistical Machine Translation" (Cho et al., 2014)
- CNN for Time Series: "Temporal Convolutional Networks" (Bai et al., 2018)
