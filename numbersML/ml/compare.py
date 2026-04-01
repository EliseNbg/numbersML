"""
Model comparison utility.

Compare multiple trained models on the same test set.

Usage:
    python -m ml.compare --models ml/models/v1/best_model.pt ml/models/v2/best_model.pt
"""

import json
import logging
import os
from typing import Dict, List

import numpy as np
import torch
from torch.utils.data import DataLoader

from ml.config import DatabaseConfig, get_default_config
from ml.dataset import WideVectorDataset, create_data_loaders
from ml.model import create_model

logger = logging.getLogger(__name__)


class ModelComparator:
    """Compare multiple models on the same test set."""

    def __init__(self, model_paths: List[str], device: str = "cpu"):
        self.device = torch.device(device)
        self.models = {}
        self.configs = {}

        for path in model_paths:
            self._load_model(path)

    def _load_model(self, model_path: str):
        """Load a model from checkpoint."""
        checkpoint = torch.load(model_path, map_location=self.device, weights_only=False)
        config = checkpoint["config"]

        # Detect model type from state dict keys
        state_keys = set(checkpoint["model_state_dict"].keys())
        if any("transformer_blocks" in k for k in state_keys):
            model_type = "transformer"
            first_weight = checkpoint["model_state_dict"]["input_proj.0.weight"]
        elif any("attention_layers" in k for k in state_keys):
            model_type = "full"
            first_weight = checkpoint["model_state_dict"]["input_proj.0.weight"]
        else:
            model_type = "simple"
            first_weight = checkpoint["model_state_dict"]["network.0.linear.weight"]
        input_dim = first_weight.shape[1]

        # Create and load model
        model = create_model(input_dim, config.model, model_type=model_type)
        model.load_state_dict(checkpoint["model_state_dict"])
        model.to(self.device)
        model.eval()

        # Store
        name = os.path.basename(os.path.dirname(model_path))
        self.models[name] = model
        self.configs[name] = config

        logger.info(f"Loaded: {name} ({model_type}, input_dim={input_dim})")

    @torch.no_grad()
    def evaluate(
        self,
        test_loader: DataLoader,
    ) -> Dict[str, Dict[str, float]]:
        """
        Evaluate all models on the test set.

        Returns:
            Dict mapping model name to metrics (loss, mae, rmse, mape)
        """
        results = {name: {"loss": 0, "mae": 0, "rmse": 0, "n_batches": 0} 
                   for name in self.models}

        criterion = torch.nn.MSELoss()

        for X, y in test_loader:
            X = X.to(self.device)
            y = y.to(self.device)

            for name, model in self.models.items():
                predictions = model(X)

                # MSE Loss
                loss = criterion(predictions, y).item()
                results[name]["loss"] += loss

                # MAE
                mae = torch.mean(torch.abs(predictions - y)).item()
                results[name]["mae"] += mae

                # RMSE
                rmse = torch.sqrt(torch.mean((predictions - y) ** 2)).item()
                results[name]["rmse"] += rmse

                results[name]["n_batches"] += 1

        # Average metrics
        for name in results:
            n = results[name]["n_batches"]
            results[name]["loss"] /= n
            results[name]["mae"] /= n
            results[name]["rmse"] /= n
            del results[name]["n_batches"]

        return results

    def compare(
        self,
        db_config: DatabaseConfig = None,
        test_hours: int = 24,
    ) -> Dict[str, Dict[str, float]]:
        """
        Full comparison pipeline.

        Args:
            db_config: Database configuration
            test_hours: Hours of test data

        Returns:
            Dict with comparison results
        """
        config = get_default_config()
        if db_config:
            config.db = db_config

        # Use config from first model for test data
        first_config = list(self.configs.values())[0]
        config.data = first_config.data

        # Override test hours
        config.data.train_hours = 0
        config.data.val_hours = 0
        config.data.test_hours = test_hours

        # Create test loader
        _, _, test_loader, _, _, _ = create_data_loaders(config.db, config.data)

        # Evaluate
        results = self.evaluate(test_loader)

        return results

    def print_comparison(self, results: Dict[str, Dict[str, float]]):
        """Print comparison table."""
        print("\n" + "=" * 70)
        print("Model Comparison")
        print("=" * 70)

        # Header
        print(f"{'Model':<20} {'MSE Loss':>12} {'MAE':>12} {'RMSE':>12}")
        print("-" * 70)

        # Sort by loss
        sorted_results = sorted(results.items(), key=lambda x: x[1]["loss"])

        for name, metrics in sorted_results:
            print(
                f"{name:<20} "
                f"{metrics['loss']:>12.6f} "
                f"{metrics['mae']:>12.6f} "
                f"{metrics['rmse']:>12.6f}"
            )

        # Best model
        best_name = sorted_results[0][0]
        print("-" * 70)
        print(f"Best model: {best_name}")

    def save_comparison(
        self,
        results: Dict[str, Dict[str, float]],
        output_path: str = "ml/models/comparison.json",
    ):
        """Save comparison results to JSON."""
        output = {
            "timestamp": str(np.datetime64("now")),
            "models": results,
            "best_model": min(results.items(), key=lambda x: x[1]["loss"])[0],
        }

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)

        print(f"\nComparison saved to {output_path}")


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Compare trained models")
    parser.add_argument(
        "--models",
        nargs="+",
        required=True,
        help="Paths to model checkpoints",
    )
    parser.add_argument(
        "--test-hours",
        type=int,
        default=24,
        help="Hours of test data (default: 24)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="ml/models/comparison.json",
        help="Output file for comparison results",
    )

    args = parser.parse_args()

    # Compare
    comparator = ModelComparator(args.models)
    results = comparator.compare(test_hours=args.test_hours)

    # Print and save
    comparator.print_comparison(results)
    comparator.save_comparison(results, args.output)


if __name__ == "__main__":
    main()
