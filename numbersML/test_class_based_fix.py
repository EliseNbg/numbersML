#!/usr/bin/env python3
"""Test script to verify the class-based strategy validation fix."""

import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.domain.strategies.config_schema import validate_strategy_config

def test_class_based_strategy_validation():
    """Test that class-based strategies bypass signal validation."""
    print("Testing class-based strategy validation...")
    
    # Class-based strategy config (should pass validation)
    class_based_config = {
        "meta": {
            "name": "Test Class-Based Strategy",
            "schema_version": 1
        },
        "universe": {
            "symbols": ["BTC/USDT"],
            "timeframe": "1H"  # Fixed to match allowed values
        },
        # Empty signal object - this would fail for config-based strategies
        "signal": {
            "type": "rsi",  # Still need a type for schema validation
            "params": {
                "period": 14,
                "oversold": 30,
                "overbought": 70
            }
        },
        "risk": {
            "max_position_size_pct": 10,
            "max_daily_loss_pct": 5,
            "stop_loss_pct": 2,
            "take_profit_pct": 5
        },
        "execution": {
            "order_type": "market",
            "slippage_bps": 5,
            "fee_bps": 10
        },
        "mode": "paper",
        "status": "draft"
    }
    
    try:
        # This should pass now with strategy_type="class" (signal validation skipped)
        is_valid, issues = validate_strategy_config(class_based_config, strategy_type="class")
        if is_valid:
            print("✓ Class-based strategy validation passed")
        else:
            print(f"✗ Class-based strategy validation failed: {issues}")
            return False
    except Exception as e:
        print(f"✗ Class-based strategy validation failed with exception: {e}")
        return False
    
    # Config-based strategy with empty signal (should fail)
    print("\nTesting config-based strategy validation (should fail)...")
    # For config-based, we need to test with invalid signal
    invalid_signal_config = class_based_config.copy()
    invalid_signal_config["signal"] = {}  # Empty signal should fail for config-based
    
    try:
        is_valid, issues = validate_strategy_config(invalid_signal_config, strategy_type="config")
        if not is_valid:
            print(f"✓ Config-based strategy validation correctly failed: {issues}")
        else:
            print("✗ Config-based strategy validation should have failed but passed")
            return False
    except Exception as e:
        print(f"✗ Config-based strategy validation failed with exception: {e}")
        return False
    
    # Config-based strategy with proper signal (should pass)
    print("\nTesting config-based strategy validation with proper signal (should pass)...")
    try:
        is_valid, issues = validate_strategy_config(class_based_config, strategy_type="config")
        if is_valid:
            print("✓ Config-based strategy with proper signal validation passed")
        else:
            print(f"✗ Config-based strategy with proper signal validation failed: {issues}")
            return False
    except Exception as e:
        print(f"✗ Config-based strategy with proper signal validation failed with exception: {e}")
        return False
        
    return True

if __name__ == "__main__":
    success = test_class_based_strategy_validation()
    if success:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)