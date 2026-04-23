# Session Checkpoint 2 — TradingTCN Normalization Fix

**Date**: 2026-04-22  
**Commit**: `7468584` + uncommitted fixes  
**Status**: Root cause identified — low-variance features (std<1e-3) are landmines in validation

## Root Cause Found
Features with near-zero training variance become landmines in validation:
- **Features 128-139**: `train_std=0.00` (constant in training). When validation mean differs, 100% of values get clipped.
- **Feature 113**: `train_mean=0.00, train_std=0.06`. In validation `val_mean=-148.50` → z-score = -2284.
- **Features 106, 102, 103, 105**: Similar pattern — tiny training std, massive validation mean shift.

These features provide zero signal in training but explode validation distributions.

## Fix Implemented (Uncommitted)
1. **Aggressive low-variance detection**: `low_var = (std < 1e-3) | (range < 1e-3)`
2. **Zero-out instead of pass-through**: Low-variance features set to 0.0 in both train and validation
3. **Safe std floor**: `max(std, 1e-3 * |mean| + 1e-6)` prevents extreme z-scores on remaining features
4. **Backtest updated**: Loads `feat_mask` from checkpoint, zeros same features
5. **Checkpoint updated**: Saves `feat_std_safe` and `feat_mask`

## Key Code Locations
- Norm fit with zero-out: `train_trading_tcn.py:262-295`
- Val explicit norm: `train_trading_tcn.py:345-376`
- Backtest norm: `backtest_trading_tcn.py:184-196`

## Next Step
Run training. Expected result: Val X mean ≈ 0, std ≈ 1 (or close), no 100% clipped features.
```bash
.venv/bin/python train_trading_tcn.py \
  --symbol DASH/USDC --hours 720 --seq-length 120 \
  --horizon 600 --loss risk_adjusted --risk-penalty 0.05 \
  --clip-returns 0.03 --lr 0.0001 --epochs 40 --stride 60
```
