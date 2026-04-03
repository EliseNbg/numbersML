#!/usr/bin/env python3
"""
Test the new CNN+GRU architecture with causal Hanning filter.

This script:
1. Trains on small dataset (1 hour)
2. Uses many epochs (200) to test overfitting capability
3. Uses shorter sequence length (100) for faster training
4. Tests if model CAN overfit (if it can't, pipeline is broken)

Expected behavior:
- Train loss should decrease to near 0
- Validation loss should decrease then increase (overfitting)
- If this doesn't happen: something is wrong with the pipeline
"""

import subprocess
import sys

def test_cnn_gru_overfitting():
    """Test if CNN+GRU model can overfit on small dataset."""
    print("="*60)
    print("Testing CNN+GRU Architecture - Overfit Test")
    print("="*60)
    print()
    print("This test checks if the model CAN learn.")
    print("If model cannot overfit small dataset → pipeline broken")
    print()
    
    cmd = [
        sys.executable, "-m", "ml.train",
        "--model", "cnn_gru",
        "--train-hours", "1",      # Small dataset
        "--epochs", "200",          # Many epochs to force overfitting
        "--seq-length", "100",      # Shorter sequences for speed
        "--lr", "0.01",             # Higher learning rate
        "--symbol", "T01/USDC"
    ]
    
    print(f"Running: {' '.join(cmd)}")
    print()
    print("-"*60)
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False, text=True)
        print()
        print("="*60)
        print("✅ CNN+GRU training completed")
        print("="*60)
        return True
    except subprocess.CalledProcessError as e:
        print()
        print("="*60)
        print(f"❌ CNN+GRU training failed with code {e.returncode}")
        print("="*60)
        return False

def test_different_horizons():
    """Test different prediction horizons."""
    print()
    print("="*60)
    print("Testing Different Prediction Horizons")
    print("="*60)
    print()
    
    horizons = [10, 30, 60]
    
    for horizon in horizons:
        print(f"\n{'='*60}")
        print(f"Testing prediction horizon: {horizon} seconds")
        print(f"{'='*60}\n")
        
        # Note: This requires modifying the config programmatically
        # For now, we'll just test the default horizon
        print(f"⚠️  Horizon testing requires config modification")
        print(f"   Edit ml/config.py: config.data.prediction_horizon = {horizon}")
        print()

if __name__ == "__main__":
    print()
    print("╔" + "="*58 + "╗")
    print("║" + " "*58 + "║")
    print("║" + "  CNN+GRU Architecture Test Suite".center(58) + "║")
    print("║" + " "*58 + "║")
    print("╚" + "="*58 + "╝")
    print()
    
    # Test 1: Overfitting
    success = test_cnn_gru_overfitting()
    
    if success:
        print()
        print("Next steps:")
        print("  1. Check if model overfitted (train loss → 0)")
        print("  2. If yes: Architecture is working ✅")
        print("  3. If no: Check data pipeline for issues ❌")
        print()
        print("  To inspect trained model:")
        print("    ls -lh ml/models/cnn_gru/")
        print()
