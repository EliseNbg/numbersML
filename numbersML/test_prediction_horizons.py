#!/usr/bin/env python3
"""
Test different prediction horizons to find the optimal one.

This script trains the CNN+GRU model with different prediction horizons
and compares the results to find the best balance between:
- Prediction accuracy (lower MAE is better)
- Prediction usefulness (longer horizon = more time to act)
- Training stability (consistent results)

Horizons tested: 10s, 30s, 60s, 300s
"""

import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime


# Configuration
SYMBOL = "T01/USDC"
TRAIN_HOURS = 2
EPOCHS = 50
SEQ_LENGTH = 100
LEARNING_RATE = 0.01
MODEL_TYPE = "cnn_gru"

HORIZONS = [10, 30, 60, 300]  # Seconds into the future


def train_with_horizon(horizon: int) -> dict:
    """Train model with specific prediction horizon."""
    print(f"\n{'='*60}")
    print(f"Training with prediction horizon: {horizon} seconds")
    print(f"{'='*60}\n")
    
    # Read config
    config_file = Path("ml/config.py")
    original_content = config_file.read_text()
    
    # Modify config to use specific horizon
    modified_content = original_content.replace(
        "prediction_horizon: int = 30",
        f"prediction_horizon: int = {horizon}"
    )
    config_file.write_text(modified_content)
    
    # Run training
    cmd = [
        sys.executable, "-m", "ml.train",
        "--model", MODEL_TYPE,
        "--train-hours", str(TRAIN_HOURS),
        "--epochs", str(EPOCHS),
        "--seq-length", str(SEQ_LENGTH),
        "--lr", str(LEARNING_RATE),
        "--symbol", SYMBOL
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        # Parse results from output
        output = result.stdout
        test_loss = None
        test_mae = None
        
        for line in output.split('\n'):
            if 'Test Loss:' in line:
                test_loss = float(line.split(':')[1].strip())
            elif 'Test MAE:' in line:
                test_mae = float(line.split(':')[1].strip())
        
        # Check if early stopping triggered
        early_stopping = 'Early stopping triggered' in output
        
        # Get best validation loss
        best_val_loss = None
        for line in output.split('\n'):
            if '[BEST]' in line and 'Val Loss:' in line:
                try:
                    val_loss_str = line.split('Val Loss:')[1].split('|')[0].strip()
                    best_val_loss = float(val_loss_str)
                except:
                    pass
        
        return {
            'horizon': horizon,
            'success': result.returncode == 0,
            'test_loss': test_loss,
            'test_mae': test_mae,
            'best_val_loss': best_val_loss,
            'early_stopping': early_stopping,
            'return_code': result.returncode
        }
        
    except subprocess.TimeoutExpired:
        print(f"❌ Training timed out for horizon {horizon}")
        return {
            'horizon': horizon,
            'success': False,
            'test_loss': None,
            'test_mae': None,
            'best_val_loss': None,
            'early_stopping': False,
            'return_code': -1,
            'error': 'Timeout'
        }
    finally:
        # Restore original config
        config_file.write_text(original_content)


def print_results(results: list):
    """Print comparison table."""
    print("\n" + "="*80)
    print("PREDICTION HORIZON COMPARISON")
    print("="*80)
    print()
    print(f"{'Horizon':>10} | {'Test Loss':>12} | {'Test MAE':>12} | {'Val Loss':>12} | {'Early Stop':>12} | {'Status':>10}")
    print("-"*80)
    
    for r in results:
        horizon = f"{r['horizon']}s"
        test_loss = f"{r['test_loss']:.4f}" if r['test_loss'] else "N/A"
        test_mae = f"{r['test_mae']:.4f}" if r['test_mae'] else "N/A"
        val_loss = f"{r['best_val_loss']:.4f}" if r['best_val_loss'] else "N/A"
        early_stop = "Yes" if r['early_stopping'] else "No"
        status = "✅ OK" if r['success'] else "❌ FAIL"
        
        print(f"{horizon:>10} | {test_loss:>12} | {test_mae:>12} | {val_loss:>12} | {early_stop:>12} | {status:>10}")
    
    print()
    
    # Find best horizon
    successful = [r for r in results if r['success'] and r['test_mae'] is not None]
    if successful:
        best = min(successful, key=lambda x: x['test_mae'])
        print(f"🏆 Best horizon: {best['horizon']}s (Test MAE: {best['test_mae']:.4f})")
        print()
        print("Recommendations:")
        print(f"  - Use horizon={best['horizon']}s for best accuracy")
        print(f"  - Shorter horizons (10-30s): Easier to predict, less time to act")
        print(f"  - Longer horizons (60-300s): Harder to predict, more time to act")
    
    print()


def save_results(results: list):
    """Save results to JSON file."""
    output_file = Path("ml/models/horizon_comparison.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        'timestamp': datetime.now().isoformat(),
        'symbol': SYMBOL,
        'train_hours': TRAIN_HOURS,
        'epochs': EPOCHS,
        'model': MODEL_TYPE,
        'results': results
    }
    
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"📊 Results saved to: {output_file}")
    print()


def main():
    """Run all horizon tests."""
    print()
    print("╔" + "="*78 + "╗")
    print("║" + " "*78 + "║")
    print("║" + "  Prediction Horizon Comparison Test".center(78) + "║")
    print("║" + " "*78 + "║")
    print("╚" + "="*78 + "╝")
    print()
    print(f"Symbol: {SYMBOL}")
    print(f"Model: {MODEL_TYPE}")
    print(f"Train hours: {TRAIN_HOURS}")
    print(f"Epochs: {EPOCHS}")
    print(f"Sequence length: {SEQ_LENGTH}")
    print(f"Learning rate: {LEARNING_RATE}")
    print()
    print("This will train multiple models with different prediction horizons.")
    print("Expected time: ~5-10 minutes total.")
    print()
    
    # Ask for confirmation
    response = input("Continue? (y/n): ").strip().lower()
    if response != 'y':
        print("Aborted.")
        return
    
    results = []
    
    # Test each horizon
    for horizon in HORIZONS:
        result = train_with_horizon(horizon)
        results.append(result)
        
        # Print intermediate results
        if result['success']:
            print(f"\n✅ Horizon {horizon}s completed")
            if result['test_mae']:
                print(f"   Test MAE: {result['test_mae']:.4f}")
        else:
            print(f"\n❌ Horizon {horizon}s failed")
    
    # Print comparison
    print_results(results)
    
    # Save results
    save_results(results)
    
    # Next steps
    print("Next steps:")
    print("  1. Review the comparison table above")
    print("  2. Update ml/config.py with best horizon:")
    print(f"     config.data.prediction_horizon = <best_horizon>")
    print("  3. Retrain final model with optimal horizon")
    print()


if __name__ == "__main__":
    main()
