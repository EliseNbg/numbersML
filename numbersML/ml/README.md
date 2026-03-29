# ML Training Pipeline Documentation

## Overview

This ML pipeline predicts crypto target values using deep learning models trained on wide vector sequences. The pipeline includes state-of-the-art transformer architectures optimized for CPU training.

## Architecture

### Data Flow

```
PostgreSQL Database
    │
    ├─ wide_vectors (X features)
    │   └─ ONE row per timestamp contains ALL symbols' data
    │      [BTC_price, BTC_rsi, ..., ETH_price, ETH_rsi, ...]
    │
    └─ candles_1s.target_value (Y target)
        └─ ONE row per symbol per timestamp
           (BTC/USDC has different target than ETH/USDC)
        
        │
        ▼
    
PyTorch Dataset
    │
    ├─ Specify target_symbol (e.g., "BTC/USDC")
    ├─ Join wide_vectors with candles_1s ON time AND symbol_id
    ├─ Normalization (Z-score)
    ├─ Sequence generation (sliding window)
    └─ Train/Val/Test split (time-based)
        
        │
        ▼
    
Neural Network Models
    │
    ├─ SimpleMLP (baseline)
    ├─ CryptoTargetModel (CNN + Attention)
    └─ CryptoTransformerModel (state-of-the-art)
        
        │
        ▼
    
Predicted target_value for SPECIFIC SYMBOL
```

### Important: Symbol-Specific Training

**The wide_vector contains ALL symbols' data, but we train to predict ONE symbol's target_value.**

Example:
- Wide vector at time T: `[BTC_price, BTC_rsi, ETH_price, ETH_rsi, ...]` (52 features)
- Target for BTC/USDC: `candles_1s.target_value WHERE symbol_id = 'BTC/USDC'`
- Target for ETH/USDC: `candles_1s.target_value WHERE symbol_id = 'ETH/USDC'`

This means:
- Same input features (wide vector)
- Different targets depending on which symbol you're predicting
- Train separate models per symbol, or train one model that includes symbol info

## Models

### 1. SimpleMLP (Baseline)

A simple MLP that only uses the last time step in the sequence.

**Architecture:**
```
Input (batch, seq_len, features)
    → Take last timestep
    → ResidualBlock(features, 512)
    → ResidualBlock(512, 256)
    → ResidualBlock(256, 128)
    → Linear(128, 1)
```

**Use case:** Baseline comparison to verify temporal modeling helps.

### 2. CryptoTargetModel (CNN + Attention)

A hybrid model combining CNN for local patterns and attention for temporal relationships.

**Architecture:**
```
Input (batch, seq_len, features)
    → Linear(features, d_model) + BatchNorm + GELU
    → Multi-scale CNN (kernel sizes: 3, 5, 7)
    → Multi-head Attention × 2
    → AdaptiveAvgPool1d
    → ResidualBlock(d_model, 256)
    → ResidualBlock(256, 128)
    → Linear(128, 1)
```

**Key features:**
- Multi-scale CNN captures patterns at different time scales
- Attention focuses on relevant time steps
- Adaptive pooling handles variable sequence lengths

### 3. CryptoTransformerModel (State-of-the-Art)

The most advanced model with modern transformer innovations.

**Architecture:**
```
Input (batch, seq_len, features)
    → Linear(features, d_model) + LayerNorm
    → Multi-scale CNN feature extraction
    → TransformerBlock × 4
        ├─ Pre-norm LayerNorm
        ├─ Multi-head Attention with RoPE
        ├─ Residual connection
        ├─ Pre-norm LayerNorm
        ├─ SwiGLU Feed-Forward
        └─ Residual connection
    → AdaptiveAvgPool1d
    → ResidualBlock(d_model, 256)
    → ResidualBlock(256, 128)
    → Linear(128, 1)
```

**Innovations:**

1. **Rotary Positional Embeddings (RoPE)**
   - Encodes relative position directly in attention
   - Better than absolute positional encoding
   - Allows model to learn temporal relationships naturally

2. **SwiGLU Activation**
   - Modern activation function (used in LLaMA, PaLM)
   - Better gradient flow than ReLU/GELU
   - Improved model capacity

3. **Pre-norm Architecture**
   - LayerNorm before attention/FFN (not after)
   - More stable training
   - Better gradient flow

4. **Multi-scale CNN + Transformer Hybrid**
   - CNN extracts local patterns (price momentum, indicator changes)
   - Transformer captures long-range dependencies
   - Best of both worlds

5. **Memory-efficient Design**
   - Optimized for CPU training
   - No flash attention dependency

## Configuration

### Model Configuration (`config.py`)

```python
@dataclass
class ModelConfig:
    # Hidden layer dimensions
    hidden_dims: List[int] = [512, 256, 128]
    
    # Dropout rate
    dropout: float = 0.2
    
    # Activation function
    activation: str = "gelu"  # relu, gelu, silu
    
    # Use residual connections
    use_residual: bool = True
    
    # Use batch normalization
    use_batch_norm: bool = True
    
    # Attention mechanism
    use_attention: bool = True
    attention_heads: int = 4
    
    # Transformer-specific settings
    transformer_layers: int = 4
    transformer_d_ff_multiplier: int = 4
    use_rope: bool = True
    use_swiglu: bool = True
    max_seq_len: int = 2048
```

### Training Configuration

```python
@dataclass
class TrainingConfig:
    # Learning rate
    learning_rate: float = 1e-3
    
    # Weight decay (L2 regularization)
    weight_decay: float = 1e-4
    
    # Number of epochs
    epochs: int = 100
    
    # Early stopping patience
    patience: int = 10
    
    # Learning rate scheduler
    scheduler: str = "cosine"  # cosine, step, plateau
    
    # Gradient clipping
    max_grad_norm: float = 1.0
```

## Usage

### Training a Model (Symbol-Specific)

```bash
# Train for BTC/USDC (default)
python -m ml.train --model simple --epochs 50 --symbol BTC/USDC

# Train for ETH/USDC
python -m ml.train --model full --epochs 100 --symbol ETH/USDC

# Train the state-of-the-art transformer model for BTC/USDC
python -m ml.train --model transformer --epochs 100 --symbol BTC/USDC
```

**Important:** Each symbol needs its own trained model because the target_value is different for each symbol.

### Hyperparameter Tuning with Optuna

```bash
# Run hyperparameter search
python -m ml.train --model transformer --tune --trials 20

# Train with specific parameters
python -m ml.train --model transformer \
    --batch-size 128 \
    --lr 0.0005 \
    --seq-length 120 \
    --epochs 150
```

### Making Predictions

```bash
# Predict using trained model
python -m ml.predict --model ml/models/best_model.pt --hours 2

# Output JSON
python -m ml.predict --model ml/models/best_model.pt --hours 6 --output predictions.json
```

### Comparing Models

```bash
# Compare multiple models
python -m ml.compare \
    --models ml/models/simple/best_model.pt \
             ml/models/full/best_model.pt \
             ml/models/transformer/best_model.pt \
    --test-hours 24
```

## Model Comparison

| Model | Parameters | Training Speed | Accuracy | Use Case |
|-------|------------|----------------|----------|----------|
| SimpleMLP | ~100K | Fast | Baseline | Quick experiments |
| CryptoTargetModel | ~500K | Medium | Good | Production baseline |
| CryptoTransformerModel | ~1M | Slower | Best | Production (best accuracy) |

## Performance Considerations

### CPU Optimization

The pipeline is optimized for CPU training:

1. **No GPU required** - All operations run efficiently on CPU
2. **Memory efficient** - Gradient checkpointing available
3. **Batch size tuning** - Smaller batches use less memory
4. **Sequence length** - Shorter sequences train faster

### Recommended Settings for CPU

```python
# For fast training (less accurate)
config.data.batch_size = 512
config.data.sequence_length = 30
config.model.hidden_dims = [256, 128, 64]

# For best accuracy (slower)
config.data.batch_size = 128
config.data.sequence_length = 120
config.model.hidden_dims = [512, 256, 128]
```

## TensorBoard Monitoring

```bash
# Start TensorBoard
tensorboard --logdir ml/logs

# Open in browser
# http://localhost:6006
```

**Metrics tracked:**
- Training loss (MSE)
- Validation loss
- Mean Absolute Error (MAE)
- Learning rate
- Model parameters

## Troubleshooting

### Out of Memory

```bash
# Reduce batch size
python -m ml.train --model transformer --batch-size 64

# Use simpler model
python -m ml.train --model simple
```

### Slow Training

```bash
# Reduce sequence length
python -m ml.train --model transformer --seq-length 30

# Use simpler model
python -m ml.train --model full
```

### Poor Convergence

```bash
# Increase learning rate
python -m ml.train --model transformer --lr 0.005

# More epochs
python -m ml.train --model transformer --epochs 200

# Try different scheduler
# Edit config.py: scheduler = "plateau"
```

## File Structure

```
ml/
├── __init__.py          # Package initialization
├── config.py            # Configuration dataclasses
├── dataset.py           # PyTorch dataset and data loading
├── model.py             # Neural network architectures
├── train.py             # Training loop and utilities
├── predict.py           # Inference script
├── compare.py           # Model comparison utility
├── models/              # Saved model checkpoints
│   ├── best_model.pt
│   └── norm_params.npz
└── logs/                # TensorBoard logs
```

## Dependencies

```bash
# Required
pip install torch numpy psycopg2-binary

# Optional (for hyperparameter tuning)
pip install optuna

# Optional (for monitoring)
pip install tensorboard
```

## References

1. **RoPE**: "RoFormer: Enhanced Transformer with Rotary Position Embedding" (Su et al., 2021)
2. **SwiGLU**: "GLU Variants Improve Transformer" (Shazeer, 2020)
3. **Pre-norm**: "On Layer Normalization in the Transformer Architecture" (Xiong et al., 2020)
