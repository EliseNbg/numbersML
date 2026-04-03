# ML Pipeline - Complete Documentation

## Overview

This is the **ML prediction pipeline** for crypto trading. It trains neural networks to predict future smoothed prices using causal Hanning filters.

**Key Innovation:** The model predicts the FUTURE, not just rebuilds a filter.

---

## 🚀 Quick Start

### 1. Train the Recommended Model

```bash
# CNN+GRU (recommended for financial time series)
python3 -m ml.train --model cnn_gru --train-hours 24 --epochs 100 --symbol T01/USDC

# Quick overfit test (should memorize small dataset)
python3 -m ml.train --model cnn_gru --train-hours 1 --epochs 50 --lr 0.01 --seq-length 100 --symbol T01/USDC
```

### 2. View Predictions in Dashboard

```bash
# Start dashboard
python3 run_dashboard.py

# Open browser
http://localhost:8000/dashboard/prediction.html
```

### 3. Compare All Models

```bash
# Train all architectures
python3 train_all_models.py

# Compare predictions
python3 -m ml.compare --models ml/models/simple/best_model.pt ml/models/cnn_gru/best_model.pt
```

---

## 📁 File Structure

```
ml/
├── __init__.py                    # Package exports
├── config.py                      # Configuration dataclasses
├── model.py                       # Neural network architectures
│   ├── CryptoTargetModel          # CNN + Attention + MLP (full)
│   ├── SimpleMLPModel             # Baseline MLP (simple)
│   ├── CryptoTransformerModel     # Transformer with RoPE (transformer)
│   └── CNN_GRUModel               # CNN + GRU (cnn_gru) ← RECOMMENDED
├── target_builder.py              # Causal Hanning filter + prediction horizon
├── dataset.py                     # PyTorch dataset for loading data
├── train.py                       # Training loop with validation
├── predict.py                     # Inference script
└── compare.py                     # Model comparison utility
```

---

## 🏗️ Architecture Overview

### Available Models

| Model | Type | Best For | CPU Speed | Parameters |
|-------|------|----------|-----------|------------|
| **CNN+GRU** | CNN + Recurrent | **Financial time series** | ⚡⚡⚡ Fast | ~500K |
| Full | CNN + Attention | Complex patterns | ⚡⚡ Medium | ~2M |
| Simple | MLP only | Baseline testing | ⚡⚡⚡⚡ Very Fast | ~300K |
| Transformer | Self-attention | Research/slow CPU | ⚡ Slow | ~5M |

### CNN+GRU Architecture (RECOMMENDED)

```
Input (seq_len × features)  [e.g., 1000 × 42]
        ↓
1D Convolution (32 channels, kernel=5)  ← Local patterns
        ↓
Batch Normalization + GELU
        ↓
1D Convolution (64 channels, kernel=5)  ← Higher-level features
        ↓
Batch Normalization + GELU + MaxPool1d(2)
        ↓
GRU (hidden=128, layers=2, dropout=0.2)  ← Temporal dependencies
        ↓
Linear (128 → 64) + GELU + Dropout
        ↓
Linear (64 → 32) + GELU
        ↓
Linear (32 → 1)  ← Regression output
```

**Why this works:**
- **CNN**: Detects local patterns (candlestick formations, indicator crossovers)
- **GRU**: Captures time-dependent relationships (trends, momentum)
- **Efficient**: Handles 1000+ timesteps on CPU easily

---

## ⚠️ Critical Concepts

### 1. Causal Hanning Filter (NO DATA LEAKAGE)

**WRONG (uses future data):**
```python
smoothed[t] = Hanning(close[t-150 : t+150])  # ❌ CHEATING!
```

**CORRECT (causal, only past):**
```python
smoothed[t] = Hanning(close[t-300 : t])  # ✅ CORRECT!
```

**Implementation:** See `ml/target_builder.py`

### 2. Prediction Horizon

**WRONG (predicts current time):**
```python
target[t] = smoothed_price[t]  # Model just learns to rebuild filter
```

**CORRECT (predicts future):**
```python
target[t] = smoothed_price[t + 30]  # Predicts 30 seconds ahead
```

### 3. Window Alignment

Three windows must be properly aligned:

| Window | Purpose | Default | Example |
|--------|---------|---------|---------|
| **Sequence Length** | Input context | 1000 steps | Uses prices[t-999 : t] |
| **Hanning Window** | Smooth target | 300 steps | Uses prices[t-299 : t] |
| **Prediction Horizon** | Future prediction | 30 steps | Predicts smoothed[t+30] |

**At time t:**
- **Input**: prices from `t-999` to `t` (past 1000 seconds)
- **Target**: smoothed price at `t+30` (30 seconds in future)
- **Hanning**: computed from prices up to `t+30` (causal)

---

## 🔧 Configuration

### Key Parameters in `ml/config.py`

```python
# Data Configuration
data.sequence_length = 1000        # Input window size (timesteps)
data.hanning_window = 300          # Causal Hanning filter window
data.prediction_horizon = 30       # Predict t+30 seconds
data.batch_size = 256              # Training batch size
data.train_hours = 168             # Training data (7 days)
data.use_indicators = True         # Include technical indicators
data.use_log_prices = True         # Use log(prices)

# Model Configuration
model.model_arch = "cnn_gru"       # Architecture type
model.gru_hidden_dim = 128         # GRU hidden size
model.gru_num_layers = 2           # Number of GRU layers
model.cnn_channels = [32, 64]      # CNN channel sizes
model.cnn_kernel_size = 5          # Convolution kernel size
model.dropout = 0.2                # Dropout rate

# Training Configuration
training.learning_rate = 1e-3      # Learning rate
training.epochs = 100              # Max training epochs
training.patience = 10             # Early stopping patience
training.scheduler = "cosine"      # LR scheduler type
```

### Command Line Arguments

```bash
python3 -m ml.train \
    --model cnn_gru \                    # Model type: cnn_gru, full, simple, transformer
    --symbol T01/USDC \                  # Target symbol
    --train-hours 24 \                   # Hours of training data
    --epochs 100 \                       # Max epochs
    --seq-length 1000 \                  # Sequence length
    --batch-size 256 \                   # Batch size
    --lr 0.001 \                         # Learning rate
    --resume ml/models/cnn_gru/checkpoint.pt  # Resume from checkpoint
```

---

## 📊 Training Process

### Training Flow

```
1. Load Data
   ├─ Fetch wide_vectors from database
   ├─ Fetch candles for target symbol
   ├─ Compute causal Hanning filter targets
   └─ Split: 70% train, 15% val, 15% test

2. Normalize Features
   ├─ Compute mean/std on training set
   ├─ Apply feature mask (remove low-variance features)
   └─ Normalize: x = (x - mean) / std

3. Train Model
   ├─ Forward pass: predict target
   ├─ Compute Huber loss
   ├─ Backward pass: compute gradients
   ├─ Gradient clipping (max_norm=1.0)
   └─ Update optimizer (AdamW)

4. Validate
   ├─ Evaluate on validation set
   ├─ Track best model (lowest val_loss)
   └─ Update learning rate (cosine scheduler)

5. Early Stopping
   ├─ Monitor validation loss
   ├─ Stop if no improvement for 10 epochs
   └─ Load best model weights

6. Save Results
   ├─ Best model: ml/models/cnn_gru/cnn_gru_42_T01USDC_20260403.pt
   ├─ Checkpoint: ml/models/cnn_gru/checkpoint.pt
   └─ Norm params: ml/models/cnn_gru/norm_params.npz
```

### Expected Training Behavior

**Normal Training:**
```
Epoch  1: Train: 47.065 | Val: 14.811
Epoch  2: Train: 10.541 | Val: 3.742   ← Rapid learning
Epoch  4: Train:  8.107 | Val: 2.830   ← Best validation
Epoch 10: Train:  7.695 | Val: 9.498   ← Overfitting starts
Epoch 14: Early stopping triggered     ← Prevents further overfitting

Test Loss: 2.535
Test MAE:  3.005
```

**Overfit Test (should memorize):**
```bash
python3 -m ml.train --model cnn_gru --train-hours 1 --epochs 50 --lr 0.01 --seq-length 100 --symbol T01/USDC
```

Expected: Train loss → 0, Val loss decreases then increases
If NOT: Pipeline has issues!

---

## 🎯 Prediction Horizons

| Horizon | Use Case | Difficulty | Description |
|---------|----------|------------|-------------|
| 10s | Very short-term scalping | Easy | Predicts 10 seconds ahead |
| **30s** | **Short-term trading** | **Medium** | **Default, good balance** |
| 60s | 1-minute predictions | Medium-Hard | Harder, needs more data |
| 300s | 5-minute trends | Hard | Long-term prediction |

**How to change:**
```python
# In ml/config.py
config.data.prediction_horizon = 60  # Predict 60 seconds ahead
```

Or in training script:
```python
config = get_default_config()
config.data.prediction_horizon = 60
trainer = Trainer(config)
trainer.train(model_type="cnn_gru")
```

---

## 📈 Feature Engineering

### Input Features (from wide_vectors)

The input vector typically contains:

| Feature Type | Transformation | Purpose |
|--------------|---------------|---------|
| Close prices | `log(price)` | Stabilizes variance |
| Volume | `log(volume + 1)` | Handles large range |
| Returns | No change | Already normalized |
| ATR | StandardScaler | Volatility measure |
| EMA (multiple) | StandardScaler | Trend indicators |
| MACD | StandardScaler | Momentum oscillator |
| RSI | StandardScaler | Overbought/oversold |
| SMA (multiple) | StandardScaler | Moving averages |
| Bollinger Bands | StandardScaler | Volatility bands |

### Feature Mask

The pipeline automatically:
1. Computes standard deviation of each feature
2. Removes features with `std < 0.01` (low variance = no information)
3. Normalizes remaining features to zero mean, unit variance

---

## 🧪 Testing

### 1. Overfit Test

**Purpose:** Verify model CAN learn (if it can't, pipeline is broken)

```bash
python3 -m ml.train --model cnn_gru --train-hours 1 --epochs 50 --lr 0.01 --seq-length 100 --symbol T01/USDC
```

**Expected:**
- Train loss decreases to near 0 (memorization)
- Validation loss decreases then increases (overfitting)
- Early stopping triggers

### 2. Different Horizons Test

**Purpose:** Compare prediction quality at different time horizons

```python
# Edit ml/config.py for each test
for horizon in [10, 30, 60, 300]:
    config.data.prediction_horizon = horizon
    # Train and compare
```

### 3. Architecture Comparison

**Purpose:** Find best model type for your data

```bash
# Train all models
python3 train_all_models.py

# Compare on same dataset
python3 -m ml.compare \
    ml/models/simple/best_model.pt \
    ml/models/cnn_gru/best_model.pt \
    ml/models/full/best_model.pt
```

---

## 🔍 Model Loading & Inference

### Loading a Trained Model

```python
import torch
from ml.model import create_model
from ml.config import get_default_config

# Load checkpoint
checkpoint = torch.load("ml/models/cnn_gru/best_model.pt", map_location="cpu")
config = checkpoint["config"]

# Load normalization params
import numpy as np
norm = np.load("ml/models/cnn_gru/norm_params.npz")
mean = norm["mean"]
std = norm["std"]
feature_mask = norm["feature_mask"]

# Create model
state_dict = checkpoint["model_state_dict"]
input_dim = state_dict["cnn1.weight"].shape[1]
model = create_model(input_dim, config.model, model_type="cnn_gru")
model.load_state_dict(state_dict)
model.eval()
```

### Running Inference

```python
# Prepare input sequence (seq_len × features)
X = ...  # Normalized wide_vectors

# Predict
with torch.no_grad():
    prediction = model(X.unsqueeze(0))  # Add batch dimension
    predicted_value = prediction.item()
```

---

## 🌐 API Integration

### REST Endpoints

The dashboard exposes these ML endpoints:

#### 1. List Available Models

```bash
GET /api/ml/models

Response:
[
  {
    "name": "cnn_gru/cnn_gru_42_T01USDC_20260403.pt",
    "type": "cnn_gru",
    "label": "CNN+GRU",
    "path": "ml/models/cnn_gru/cnn_gru_42_T01USDC_20260403.pt",
    "size_mb": 2.33,
    "modified": "2026-04-03T09:44:00"
  }
]
```

#### 2. Run Prediction

```bash
GET /api/ml/predict?symbol=T01/USDC&model=cnn_gru/best_model.pt&hours=2

Response:
{
  "symbol": "T01/USDC",
  "model": "cnn_gru/best_model.pt",
  "candles_count": 7200,
  "targets_count": 7200,
  "predictions_count": 6201,
  "candles": [...],
  "targets": [...],
  "predictions": [...]
}
```

### Dashboard Integration

The prediction page (`dashboard/prediction.html`) automatically:
1. Fetches available models from API
2. Populates dropdown menu
3. Shows recommendation for CNN+GRU
4. Loads and displays predictions on chart

---

## 📚 Theoretical Background

### Why Causal Convolutions?

Standard convolutions use future data:
```
y[t] = sum(w[i] * x[t+i])  for i in [-k, k]  ← Uses x[t+k] (future!)
```

Causal convolutions only use past:
```
y[t] = sum(w[i] * x[t-i])  for i in [0, k]   ← Only x[t-k] to x[t] (past!)
```

**Reference:** WaveNet paper (van den Oord et al., 2016)

### Why GRU instead of LSTM?

GRU has fewer parameters than LSTM but similar performance:
- **LSTM**: 4 gates (input, forget, cell, output)
- **GRU**: 3 gates (reset, update, candidate)

**Benefits:**
- Faster training
- Less memory
- Similar accuracy for most tasks

### Why Huber Loss instead of MSE?

Huber loss is more robust to outliers:
```
L(y, ŷ) = 0.5 * (y - ŷ)²           if |y - ŷ| < δ
L(y, ŷ) = δ * (|y - ŷ| - 0.5 * δ) otherwise
```

- Small errors: behaves like MSE (smooth gradients)
- Large errors: behaves like MAE (robust to outliers)
- Default δ = 1.0

---

## 🐛 Troubleshooting

### Issue: Training fails with "Insufficient samples"

**Cause:** Not enough data in database

**Solution:**
```bash
# Check available data
python3 -c "
import psycopg2
conn = psycopg2.connect(host='localhost', dbname='crypto_trading', user='crypto', password='crypto_secret')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM wide_vectors')
print(f'Wide vectors: {cur.fetchone()[0]}')
cur.execute('SELECT COUNT(*) FROM candles_1s')
print(f'Candles: {cur.fetchone()[0]}')
"
```

### Issue: Model doesn't learn (loss stays high)

**Possible causes:**
1. Wrong target calculation (check causal filter)
2. Features not normalized
3. Learning rate too low/high
4. Sequence length too short

**Debug steps:**
```bash
# Run overfit test
python3 -m ml.train --model cnn_gru --train-hours 1 --epochs 50 --lr 0.01 --symbol T01/USDC

# If still doesn't learn: pipeline is broken
# If it overfits: need more data or better features
```

### Issue: Predictions look too smooth

**This is expected!** The target IS smooth (Hanning filter).

- If you want sharp predictions: Use MAE or Huber loss
- But smooth predictions are correct for trend following

### Issue: CUDA out of memory

**Solution:** Reduce batch size or sequence length:
```bash
python3 -m ml.train --model cnn_gru --batch-size 128 --seq-length 500 --symbol T01/USDC
```

---

## 📖 References

### Papers
- **WaveNet**: van den Oord et al. "WaveNet: A Generative Model for Raw Audio" (2016)
- **GRU**: Cho et al. "Learning Phrase Representations using RNN Encoder-Decoder" (2014)
- **TCN**: Bai et al. "Temporal Convolutional Networks" (2018)
- **Transformer**: Vaswani et al. "Attention Is All You Need" (2017)
- **RoPE**: Su et al. "RoFormer: Enhanced Transformer with Rotary Position Embedding" (2021)
- **SwiGLU**: Shazeer. "GLU Variants Improve Transformer" (2020)

### Books
- Advances in Financial Machine Learning - Marcos Lopez de Prado
- Machine Learning for Algorithmic Trading - Stefan Jansen

---

## ✅ Checklist for New Users

- [ ] Read "Critical Concepts" section (causal filter, prediction horizon)
- [ ] Run overfit test to verify pipeline
- [ ] Train CNN+GRU model on your symbol
- [ ] View predictions in dashboard
- [ ] Experiment with different horizons
- [ ] Compare with other architectures

---

**Last Updated:** 2026-04-03  
**Version:** 0.2.0  
**Status:** ✅ Production Ready
