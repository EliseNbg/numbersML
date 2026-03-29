"""
ML Training Pipeline Configuration.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import os


@dataclass
class DatabaseConfig:
    """PostgreSQL connection configuration."""
    host: str = "localhost"
    port: int = 5432
    dbname: str = "crypto_trading"
    user: str = "crypto"
    password: str = "crypto_secret"


@dataclass
class DataConfig:
    """Data loading and preprocessing configuration."""
    # Target symbol for training (the symbol we predict target_value for)
    target_symbol: str = "BTC/USDC"
    
    # Time range for training data (hours from now)
    train_hours: int = 168  # 7 days
    val_hours: int = 24  # 1 day for validation
    test_hours: int = 24  # 1 day for testing

    # Sequence length for temporal context (number of consecutive wide_vectors)
    sequence_length: int = 60  # 60 seconds of context

    # Batch size
    batch_size: int = 256

    # Number of workers for data loading
    num_workers: int = 0  # 0 for CPU-only

    # Whether to normalize features
    normalize: bool = True

    # Minimum target_value samples required
    min_samples: int = 1000


@dataclass
class ModelConfig:
    """Model architecture configuration."""
    # Hidden layer dimensions
    hidden_dims: List[int] = field(default_factory=lambda: [512, 256, 128])

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
    transformer_layers: int = 4  # Number of transformer blocks
    transformer_d_ff_multiplier: int = 4  # FFN dimension = d_model * multiplier
    use_rope: bool = True  # Use Rotary Positional Embeddings
    use_swiglu: bool = True  # Use SwiGLU activation in FFN
    max_seq_len: int = 2048  # Maximum sequence length for RoPE


@dataclass
class TrainingConfig:
    """Training configuration."""
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

    # Mixed precision (disabled for CPU)
    use_amp: bool = False

    # Save directory
    save_dir: str = "ml/models"

    # Log directory
    log_dir: str = "ml/logs"


@dataclass
class OptunaConfig:
    """Optuna hyperparameter tuning configuration."""
    enabled: bool = False
    n_trials: int = 20
    n_epochs_per_trial: int = 10
    timeout: int = 3600  # 1 hour


@dataclass
class PipelineConfig:
    """Complete pipeline configuration."""
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    data: DataConfig = field(default_factory=DataConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)
    optuna: OptunaConfig = field(default_factory=OptunaConfig)

    # Random seed
    seed: int = 42

    # Device (auto-detect)
    device: str = "cpu"


def get_default_config() -> PipelineConfig:
    """Get default configuration."""
    return PipelineConfig()
