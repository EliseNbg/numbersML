#!/usr/bin/env python3
"""
Train all three model types on T01/USDC data.
Each model is saved in its own directory without overriding root best_model.
"""

import asyncio
import subprocess
import sys
from pathlib import Path

def run_training(model_type: str, symbol: str = "T01/USDC", hours: int = 2) -> int:
    """Run training for a specific model type."""
    print(f"\n{'='*60}")
    print(f"Training {model_type.upper()} model on {symbol}")
    print(f"{'='*60}")
    
    cmd = [
        sys.executable, "-m", "ml.train",
        "--model", model_type,
        "--train-hours", str(hours),
        "--epochs", "100",
        "--seq-length", "10",
        "--lr", "0.001",
        "--symbol", symbol
    ]
    
    print(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False, text=True)
        print(f"✅ {model_type} training completed successfully")
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"❌ {model_type} training failed with code {e.returncode}")
        return e.returncode

def move_model_files(model_type: str) -> None:
    """Move trained model files to their own directory."""
    src_dir = Path("ml/models")
    dest_dir = src_dir / model_type
    dest_dir.mkdir(exist_ok=True, parents=True)
    
    # Move best model
    src_model = src_dir / "best_model.pt"
    dest_model = dest_dir / "best_model.pt"
    if src_model.exists():
        src_model.rename(dest_model)
        print(f"Moved {src_model} -> {dest_model}")
    
    # Move normalization params
    src_norm = src_dir / "norm_params.npz"
    dest_norm = dest_dir / "norm_params.npz"
    if src_norm.exists():
        src_norm.rename(dest_norm)
        print(f"Moved {src_norm} -> {dest_norm}")
    
    # Move checkpoint if exists
    src_checkpoint = src_dir / "checkpoint.pt"
    dest_checkpoint = dest_dir / "checkpoint.pt"
    if src_checkpoint.exists():
        src_checkpoint.rename(dest_checkpoint)
        print(f"Moved {src_checkpoint} -> {dest_checkpoint}")

async def main():
    symbol = "T01/USDC"
    train_hours = 2
    
    print(f"Starting training for all three model types on {symbol}")
    print(f"Training with {train_hours} hours of data")
    
    # Train each model sequentially
    for model in ["simple", "full", "transformer"]:
        exit_code = run_training(model, symbol, train_hours)
        if exit_code == 0:
            move_model_files(model)
    
    print("\n✅ All models trained successfully")
    print("\nModel locations:")
    for model in ["simple", "full", "transformer"]:
        print(f"  {model}: ml/models/{model}/best_model.pt")

if __name__ == "__main__":
    asyncio.run(main())
