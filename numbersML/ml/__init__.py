"""
ML Training Pipeline for Crypto Target Prediction.

Modules:
    config: Configuration dataclasses
    dataset: PyTorch dataset for loading wide_vectors + target_values
    model: Neural network architectures
    train: Training loop with validation, LR scheduling, early stopping
    predict: Inference script
    compare: Model comparison utility

Usage:
    # Train model
    python -m ml.train --model full --epochs 100

    # Train with hyperparameter tuning
    python -m ml.train --tune --trials 20

    # Predict
    python -m ml.predict --model ml/models/best_model.pt --hours 2

    # Compare models
    python -m ml.compare --models ml/models/v1/best_model.pt ml/models/v2/best_model.pt
"""

from ml.config import PipelineConfig, get_default_config
from ml.dataset import WideVectorDataset, create_data_loaders
from ml.model import CryptoTargetModel, SimpleMLPModel, CNN_GRUModel, create_model
from ml.train import Trainer, run_optuna_tuning
from ml.predict import Predictor
from ml.compare import ModelComparator
from ml.target_builder import causal_hanning_filter, compute_target_with_horizon

__version__ = "0.2.0"
