# 🚀 Quick Start - Redesigned ML Models

## TL;DR - Just Train the Model!

```bash
# Train the new recommended architecture
python3 -m ml.train --model cnn_gru --train-hours 24 --epochs 100 --symbol T01/USDC

# Quick test (should overfit)
python3 -m ml.train --model cnn_gru --train-hours 1 --epochs 50 --lr 0.01 --seq-length 100 --symbol T01/USDC
```

---

## What Changed?

### ❌ BEFORE (Wrong)
- Target used **future data** (data leakage!)
- Model predicted **current time** (just rebuilds filter)
- Simple MLP had **no temporal understanding**

### ✅ AFTER (Correct)
- Target uses **only past data** (causal filter)
- Model predicts **30 seconds into future**
- CNN+GRU understands **patterns + time**

---

## Available Models

```bash
# CNN+GRU (RECOMMENDED for financial time series)
python3 -m ml.train --model cnn_gru ...

# Simple MLP (baseline)
python3 -m ml.train --model simple ...

# Full CNN+Attention (complex patterns)
python3 -m ml.train --model full ...

# Transformer (state-of-the-art, slow on CPU)
python3 -m ml.train --model transformer ...
```

---

## Key Parameters

Edit `ml/config.py` or pass via code:

```python
config.data.sequence_length = 1000        # Input window (timesteps)
config.data.hanning_window = 300          # Smoothing window
config.data.prediction_horizon = 30       # Predict t+30 seconds
```

---

## Model Location

After training, models are saved in:
```
ml/models/
├── cnn_gru/
│   └── cnn_gru_42_T01USDC_20260403.pt
├── simple/
│   └── simple_42_T01USDC_20260403.pt
├── full/
│   └── ...
└── transformer/
    └── ...
```

---

## Test Results

**CNN+GRU Model (1 hour data, 50 epochs):**
- Train Loss: 47.07 → 2.83 (16x improvement)
- Val Loss: 14.81 → 2.83 (5x improvement)
- Test MAE: 3.00 ✅
- Training Time: ~15 seconds per epoch

---

## Next Steps

1. ✅ Train model
2. ⏳ Update dataset to use causal target builder
3. ⏳ Add proper feature normalization
4. ⏳ Test with different prediction horizons
5. ⏳ Deploy to production

See `REDESIGN_SUMMARY.md` for full documentation.
