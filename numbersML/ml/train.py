"""
Training pipeline for ML target prediction.

Features:
- Training loop with validation
- Learning rate scheduling (cosine, step, plateau)
- Early stopping
- Model checkpointing
- TensorBoard logging
- Optuna hyperparameter tuning
- Gradient clipping
"""

import logging
import os
import time
from datetime import datetime
from typing import Dict, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import (
    CosineAnnealingLR,
    ReduceLROnPlateau,
    StepLR,
)
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter

from ml.config import PipelineConfig, get_default_config
from ml.dataset import create_data_loaders
from ml.model import create_model

logger = logging.getLogger(__name__)


class EarlyStopping:
    """Early stopping to prevent overfitting."""

    def __init__(self, patience: int = 10, min_delta: float = 1e-6):
        self.patience = patience
        self.min_delta = min_delta
        self.counter = 0
        self.best_loss = None
        self.should_stop = False

    def __call__(self, val_loss: float) -> bool:
        if self.best_loss is None:
            self.best_loss = val_loss
        elif val_loss > self.best_loss - self.min_delta:
            self.counter += 1
            if self.counter >= self.patience:
                self.should_stop = True
        else:
            self.best_loss = val_loss
            self.counter = 0

        return self.should_stop


class Trainer:
    """Main training class."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.device = torch.device(config.device)

        # Create directories
        os.makedirs(config.training.save_dir, exist_ok=True)
        os.makedirs(config.training.log_dir, exist_ok=True)

        # Set random seed
        torch.manual_seed(config.seed)
        np.random.seed(config.seed)

        # TensorBoard writer
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.writer = SummaryWriter(
            log_dir=os.path.join(config.training.log_dir, timestamp)
        )

        # Training state
        self.best_val_loss = float("inf")
        self.best_model_path = None
        
        # Initialize attributes to avoid AttributeError
        self.model_type = "full"  # Default, will be overridden in train()
        self.norm_path = None  # Will be set in train()
        self.train_loader = None  # Will be set in setup_data()

    def setup_data(self) -> Tuple[DataLoader, DataLoader, DataLoader]:
        """Create data loaders."""
        self.train_loader, self.val_loader, self.test_loader, self.mean, self.std, self.feature_mask = (
            create_data_loaders(self.config.db, self.config.data)
        )

        # Save normalization parameters and feature mask
        norm_path = os.path.join(self.config.training.save_dir, "norm_params.npz")
        np.savez(norm_path, mean=self.mean, std=self.std, feature_mask=self.feature_mask)
        logger.info(f"Normalization params saved to {norm_path}")

        # Auto-adjust config for small datasets
        n_train = len(self.train_loader.dataset)
        if n_train < 200:
            logger.info(f"Small dataset detected ({n_train} samples). Adjusting config.")
            # Reduce model size
            if self.config.model.hidden_dims[0] > 128:
                self.config.model.hidden_dims = [128, 64, 32]
            # Reduce dropout for small data
            if self.config.model.dropout > 0.1:
                self.config.model.dropout = 0.1
            # Lower learning rate
            if self.config.training.learning_rate > 5e-4:
                self.config.training.learning_rate = 5e-4

        return self.train_loader, self.val_loader, self.test_loader

    def setup_model(self, input_dim: int, model_type: str = "full") -> nn.Module:
        """Create model and optimizer."""
        self.model = create_model(input_dim, self.config.model, model_type)
        self.model.to(self.device)

        # Count parameters
        total_params = sum(p.numel() for p in self.model.parameters())
        trainable_params = sum(
            p.numel() for p in self.model.parameters() if p.requires_grad
        )
        logger.info(f"Total parameters: {total_params:,}")
        logger.info(f"Trainable parameters: {trainable_params:,}")

        # Optimizer
        self.optimizer = AdamW(
            self.model.parameters(),
            lr=self.config.training.learning_rate,
            weight_decay=self.config.training.weight_decay,
        )

        # Loss function - Huber loss is more robust to outliers than MSE
        self.criterion = nn.HuberLoss(delta=1.0)

        # Learning rate scheduler
        if self.config.training.scheduler == "cosine":
            self.scheduler = CosineAnnealingLR(
                self.optimizer, T_max=self.config.training.epochs
            )
        elif self.config.training.scheduler == "step":
            self.scheduler = StepLR(
                self.optimizer, step_size=10, gamma=0.5
            )
        elif self.config.training.scheduler == "plateau":
            self.scheduler = ReduceLROnPlateau(
                self.optimizer, mode="min", patience=5, factor=0.5
            )
        else:
            self.scheduler = None

        # Early stopping
        self.early_stopping = EarlyStopping(patience=self.config.training.patience)

        return self.model

    def train_epoch(self, epoch: int) -> Dict[str, float]:
        """Train for one epoch."""
        self.model.train()
        total_loss = 0.0
        total_mae = 0.0
        n_batches = 0

        for batch_idx, (X, y) in enumerate(self.train_loader):
            X = X.to(self.device)
            y = y.to(self.device)

            # Forward pass
            self.optimizer.zero_grad()
            predictions = self.model(X)
            loss = self.criterion(predictions, y)

            # Backward pass
            loss.backward()

            # Gradient clipping
            if self.config.training.max_grad_norm > 0:
                nn.utils.clip_grad_norm_(
                    self.model.parameters(), self.config.training.max_grad_norm
                )

            self.optimizer.step()

            # Metrics
            total_loss += loss.item()
            total_mae += torch.mean(torch.abs(predictions - y)).item()
            n_batches += 1

            # Log to TensorBoard every 100 batches
            if batch_idx % 100 == 0:
                global_step = epoch * len(self.train_loader) + batch_idx
                self.writer.add_scalar("train/batch_loss", loss.item(), global_step)

        avg_loss = total_loss / n_batches
        avg_mae = total_mae / n_batches

        return {"loss": avg_loss, "mae": avg_mae}

    @torch.no_grad()
    def validate(self, loader: DataLoader) -> Dict[str, float]:
        """Validate the model."""
        self.model.eval()
        total_loss = 0.0
        total_mae = 0.0
        n_batches = 0

        for X, y in loader:
            X = X.to(self.device)
            y = y.to(self.device)

            predictions = self.model(X)
            loss = self.criterion(predictions, y)

            total_loss += loss.item()
            total_mae += torch.mean(torch.abs(predictions - y)).item()
            n_batches += 1

        return {
            "loss": total_loss / n_batches,
            "mae": total_mae / n_batches,
        }

    def save_checkpoint(self, epoch: int, val_loss: float, is_best: bool = False):
        """Save model checkpoint."""
        checkpoint = {
            "epoch": epoch,
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "val_loss": val_loss,
            "config": self.config,
        }

        # Save latest checkpoint
        path = os.path.join(self.config.training.save_dir, "checkpoint.pt")
        torch.save(checkpoint, path)

        # Save best model to model type directory with proper naming
        if is_best:
            # Create model type directory
            model_dir = os.path.join(self.config.training.save_dir, self.model_type)
            os.makedirs(model_dir, exist_ok=True)

            # Generate proper filename: modelName_wideVectorDim_Symbol_Date.pt
            timestamp = datetime.now().strftime("%Y%m%d")
            
            # Get input dimension from model config or sample data
            if hasattr(self, 'train_loader') and self.train_loader and len(self.train_loader.dataset) > 0:
                input_dim = self.train_loader.dataset[0][0].shape[-1]
            else:
                # Fallback: try to get from model's first layer
                input_dim = self.config.model.hidden_dims[0] if self.config.model.hidden_dims else 128
            
            symbol = self.config.data.target_symbol.replace("/", "")
            filename = f"{self.model_type}_{input_dim}_{symbol}_{timestamp}.pt"

            best_path = os.path.join(model_dir, filename)
            torch.save(checkpoint, best_path)
            self.best_model_path = best_path

            # Also save norm params in model directory
            if hasattr(self, 'norm_path') and os.path.exists(self.norm_path):
                import shutil
                norm_dest = os.path.join(model_dir, "norm_params.npz")
                shutil.copyfile(self.norm_path, norm_dest)

            print(f"New best model saved: {best_path}")

    def train(
        self,
        model_type: str = "full",
        resume_from: Optional[str] = None,
    ) -> Dict[str, float]:
        """
        Full training loop.

        Args:
            model_type: "full" or "simple" model
            resume_from: Path to checkpoint to resume from

        Returns:
            Dictionary with final metrics
        """
        self.model_type = model_type
        
        # Setup data
        self.setup_data()
        self.norm_path = os.path.join(self.config.training.save_dir, "norm_params.npz")

        # Get input dimension
        sample_X, _ = next(iter(self.train_loader))
        input_dim = sample_X.shape[-1]
        logger.info(f"Input dimension: {input_dim}")

        # Setup model
        self.setup_model(input_dim, model_type)

        # Resume from checkpoint
        start_epoch = 0
        if resume_from and os.path.exists(resume_from):
            checkpoint = torch.load(resume_from, map_location=self.device, weights_only=False)
            
            # Check if feature dimensions match
            saved_input_dim = checkpoint["model_state_dict"]["feature_proj.1.weight"].shape[1]
            if saved_input_dim != input_dim:
                logger.warning(
                    f"Feature dimension mismatch: checkpoint has {saved_input_dim}, current data has {input_dim}. "
                    f"Using saved feature mask from checkpoint."
                )
                # TODO: Restore feature mask from checkpoint and reload datasets
                # For now, this will fail if feature dimensions don't match
                raise RuntimeError(
                    f"Cannot resume: feature dimension mismatch ({saved_input_dim} vs {input_dim}). "
                    f"Train from scratch or use same data window."
                )
            
            self.model.load_state_dict(checkpoint["model_state_dict"])
            self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
            start_epoch = checkpoint["epoch"] + 1
            self.best_val_loss = checkpoint["val_loss"]
            print(f"Resumed from epoch {start_epoch}")

        # Training loop
        print(f"\nStarting training for {self.config.training.epochs} epochs...")
        print("-" * 60)

        for epoch in range(start_epoch, self.config.training.epochs):
            epoch_start = time.time()

            # Train
            train_metrics = self.train_epoch(epoch)

            # Validate
            val_metrics = self.validate(self.val_loader)

            # Update scheduler
            if self.scheduler is not None:
                if isinstance(self.scheduler, ReduceLROnPlateau):
                    self.scheduler.step(val_metrics["loss"])
                else:
                    self.scheduler.step()

            # Get current learning rate
            current_lr = self.optimizer.param_groups[0]["lr"]

            # Log to TensorBoard
            self.writer.add_scalar("train/loss", train_metrics["loss"], epoch)
            self.writer.add_scalar("train/mae", train_metrics["mae"], epoch)
            self.writer.add_scalar("val/loss", val_metrics["loss"], epoch)
            self.writer.add_scalar("val/mae", val_metrics["mae"], epoch)
            self.writer.add_scalar("learning_rate", current_lr, epoch)

            # Print progress
            epoch_time = time.time() - epoch_start
            is_best = val_metrics["loss"] < self.best_val_loss

            if is_best:
                self.best_val_loss = val_metrics["loss"]

            print(
                f"Epoch {epoch + 1:3d}/{self.config.training.epochs} | "
                f"Train Loss: {train_metrics['loss']:.6f} | "
                f"Val Loss: {val_metrics['loss']:.6f} | "
                f"Val MAE: {val_metrics['mae']:.6f} | "
                f"LR: {current_lr:.2e} | "
                f"Time: {epoch_time:.1f}s"
                + (" [BEST]" if is_best else "")
            )

            # Save checkpoint
            self.save_checkpoint(epoch, val_metrics["loss"], is_best)

            # Early stopping
            if self.early_stopping(val_metrics["loss"]):
                print(f"\nEarly stopping triggered at epoch {epoch + 1}")
                break

        # Final evaluation on test set
        print("\n" + "=" * 60)
        print("Final evaluation on test set:")
        print("=" * 60)

        # Load best model
        if self.best_model_path:
            checkpoint = torch.load(self.best_model_path, map_location=self.device, weights_only=False)
            self.model.load_state_dict(checkpoint["model_state_dict"])

        test_metrics = self.validate(self.test_loader)
        print(f"Test Loss: {test_metrics['loss']:.6f}")
        print(f"Test MAE:  {test_metrics['mae']:.6f}")

        # Log final metrics
        self.writer.add_hparams(
            {
                "model_type": model_type,
                "hidden_dims": str(self.config.model.hidden_dims),
                "dropout": self.config.model.dropout,
                "lr": self.config.training.learning_rate,
                "batch_size": self.config.data.batch_size,
                "seq_len": self.config.data.sequence_length,
            },
            {
                "test_loss": test_metrics["loss"],
                "test_mae": test_metrics["mae"],
                "best_val_loss": self.best_val_loss,
            },
        )

        self.writer.close()

        return test_metrics


def run_optuna_tuning(config: PipelineConfig, n_trials: int = 20):
    """
    Run Optuna hyperparameter tuning.

    Searches over:
    - hidden_dims (architecture)
    - dropout
    - learning_rate
    - batch_size
    - sequence_length
    """
    try:
        import optuna
    except ImportError:
        print("Optuna not installed. Install with: pip install optuna")
        return None

    def objective(trial: optuna.Trial) -> float:
        # Sample hyperparameters
        trial_config = PipelineConfig()
        trial_config.db = config.db
        trial_config.model.hidden_dims = [
            trial.suggest_categorical("hidden_1", [128, 256, 512, 1024]),
            trial.suggest_categorical("hidden_2", [64, 128, 256, 512]),
            trial.suggest_categorical("hidden_3", [32, 64, 128]),
        ]
        trial_config.model.dropout = trial.suggest_float("dropout", 0.1, 0.5)
        trial_config.training.learning_rate = trial.suggest_float(
            "lr", 1e-5, 1e-2, log=True
        )
        trial_config.data.batch_size = trial.suggest_categorical(
            "batch_size", [64, 128, 256, 512]
        )
        trial_config.data.sequence_length = trial.suggest_categorical(
            "seq_length", [30, 60, 120, 180]
        )
        trial_config.training.epochs = config.optuna.n_epochs_per_trial

        # Train
        trainer = Trainer(trial_config)
        metrics = trainer.train(model_type="full")

        return metrics["loss"]

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=n_trials, timeout=config.optuna.timeout)

    print("\nBest trial:")
    print(f"  Value: {study.best_trial.value:.6f}")
    print("  Params:")
    for key, value in study.best_trial.params.items():
        print(f"    {key}: {value}")

    return study.best_trial.params


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Train ML target prediction model")
    parser.add_argument(
        "--model",
        choices=["full", "simple", "transformer", "cnn_gru"],
        default="cnn_gru",
        help="Model type: full (CNN+Attention), simple (MLP), transformer (state-of-the-art), cnn_gru (CNN+GRU - RECOMMENDED for financial time series)",
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Path to checkpoint to resume from",
    )
    parser.add_argument(
        "--tune",
        action="store_true",
        help="Run Optuna hyperparameter tuning",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=20,
        help="Number of Optuna trials (default: 20)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=100,
        help="Number of training epochs (default: 100)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=256,
        help="Batch size (default: 256)",
    )
    parser.add_argument(
        "--lr",
        type=float,
        default=1e-3,
        help="Learning rate (default: 0.001)",
    )
    parser.add_argument(
        "--seq-length",
        type=int,
        default=120,
        help="Sequence length in seconds (default: 120)",
    )
    parser.add_argument(
        "--train-hours",
        type=int,
        default=168,
        help="Training data hours (default: 168 = 7 days)",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTC/USDC",
        help="Target symbol to train for (default: BTC/USDC)",
    )

    args = parser.parse_args()

    # Create config
    config = get_default_config()
    config.training.epochs = args.epochs
    config.data.batch_size = args.batch_size
    config.training.learning_rate = args.lr
    config.data.sequence_length = args.seq_length
    config.data.train_hours = args.train_hours
    config.data.target_symbol = args.symbol
    config.optuna.n_trials = args.trials

    if args.tune:
        print("Running Optuna hyperparameter tuning...")
        best_params = run_optuna_tuning(config, n_trials=args.trials)
        if best_params:
            # Update config with best params
            config.model.hidden_dims = [
                best_params.get("hidden_1", 512),
                best_params.get("hidden_2", 256),
                best_params.get("hidden_3", 128),
            ]
            config.model.dropout = best_params.get("dropout", 0.2)
            config.training.learning_rate = best_params.get("lr", 1e-3)
            config.data.batch_size = best_params.get("batch_size", 256)
            config.data.sequence_length = best_params.get("seq_length", 60)

            # Train final model with best params
            print("\nTraining final model with best parameters...")
            trainer = Trainer(config)
            trainer.train(model_type=args.model)
    else:
        trainer = Trainer(config)
        trainer.train(model_type=args.model, resume_from=args.resume)


if __name__ == "__main__":
    main()
