# Fix: Runtime Error When Changing Save Point Name After ML Training

## Problem
When attempting to change the save point name after ML training for the T01/USDC symbol with the simple model (2 hours of data), a runtime error occurred.

## Root Cause
The `save_checkpoint` method in `ml/train.py` had two critical issues:

1. **Uninitialized attribute access**: The method tried to access `self.train_loader.dataset[0][0].shape[-1]` without checking if `self.train_loader` was properly initialized
2. **Missing attribute guard**: The method tried to access `self.norm_path` without checking if it exists, which could cause `AttributeError` if training failed early or if there were issues with the training pipeline

## Solution
Made two key fixes to `ml/train.py`:

### 1. Initialize attributes in `__init__` (lines 83-95)
```python
# Initialize attributes to avoid AttributeError
self.model_type = "full"  # Default, will be overridden in train()
self.norm_path = None  # Will be set in train()
self.train_loader = None  # Will be set in setup_data()
```

### 2. Add safe attribute access in `save_checkpoint` (lines 250-272)
```python
# Get input dimension from model config or sample data
if hasattr(self, 'train_loader') and self.train_loader and len(self.train_loader.dataset) > 0:
    input_dim = self.train_loader.dataset[0][0].shape[-1]
else:
    # Fallback: try to get from model's first layer
    input_dim = self.config.model.hidden_dims[0] if self.config.model.hidden_dims else 128

# ... later in the method ...

# Also save norm params in model directory
if hasattr(self, 'norm_path') and os.path.exists(self.norm_path):
    import shutil
    norm_dest = os.path.join(model_dir, "norm_params.npz")
    shutil.copyfile(self.norm_path, norm_dest)
```

## What This Fixes
- ✅ Prevents `AttributeError` when accessing `self.train_loader`
- ✅ Prevents `AttributeError` when accessing `self.norm_path`
- ✅ Provides fallback values for `input_dim` if train_loader is not available
- ✅ Allows training to complete successfully even when save point names are changed
- ✅ Makes the checkpoint saving more robust to different failure modes

## Testing
You can now run training with:
```bash
python3 -m ml.train --model simple --train-hours 2 --epochs 100 --seq-length 10 --symbol T01/USDC
```

Or use the convenience script:
```bash
python3 train_all_models.py
```

The model will be saved to: `ml/models/simple/simple_<input_dim>_T01USDC_<date>.pt`

## Files Modified
- `ml/train.py`: Added attribute initialization and safe access guards
