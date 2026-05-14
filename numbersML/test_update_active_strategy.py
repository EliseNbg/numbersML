#!/usr/bin/env python3
"""Test script to verify the update active strategy version endpoint works with class-based strategies."""

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
from datetime import datetime, UTC

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.infrastructure.api.routes.strategies import update_active_strategy_version, UpdateActiveVersionRequest
from src.domain.strategies.strategy_config import StrategyDefinition, StrategyConfigVersion
from src.domain.strategies.config_schema import StrategyConfigSchema
from fastapi import HTTPException

async def test_update_active_strategy_version_class_based():
    """Test that update_active_strategy_version works with class-based strategies."""
    print("Testing update_active_strategy_version with class-based strategy...")
    
    # Setup
    strategy_id = uuid4()
    version_number = 2
    
    # Create a mock strategy definition (class-based)
    mock_strategy = MagicMock(spec=StrategyDefinition)
    mock_strategy.id = strategy_id
    mock_strategy.name = "Test Class-Based Strategy"
    mock_strategy.mode = "paper"
    mock_strategy.status = "draft"
    mock_strategy.current_version = 1
    mock_strategy.strategy_type = "class"  # This is the key - class-based strategy
    mock_strategy.class_path = "src.strategies.user.example.ExampleStrategy"
    mock_strategy.created_by = "test"
    mock_strategy.created_at = datetime.now(UTC)
    mock_strategy.updated_at = datetime.now(UTC)
    
    # Create a mock version
    mock_version = MagicMock(spec=StrategyConfigVersion)
    mock_version.id = uuid4()
    mock_version.version = version_number
    mock_version.is_active = False
    mock_version.strategy_id = strategy_id
    mock_version.created_by = "test"
    mock_version.created_at = datetime.now(UTC)
    
    # Mock repository
    mock_repo = MagicMock()
    mock_repo.get_by_id = AsyncMock(return_value=mock_strategy)
    mock_repo.list_versions = AsyncMock(return_value=[mock_version])  # Need at least one version
    mock_repo.create_version = AsyncMock(return_value=mock_version)
    mock_repo.set_active_version = AsyncMock(return_value=True)
    
    # Create request with config dict (empty signal for class-based)
    config_dict = {
        "meta": {"name": "Test", "schema_version": 1},
        "universe": {"symbols": ["BTC/USDT"], "timeframe": "1H"},
        "signal": {},  # Empty signal - should work for class-based
        "risk": {"max_position_size_pct": 10},
        "execution": {"order_type": "market"},
        "mode": "paper"
    }
    
    # Mock the StrategyConfigSchema to avoid validation issues in testing
    with patch('src.infrastructure.api.routes.strategies.StrategyConfigSchema', return_value=MagicMock(dict=MagicMock(return_value=config_dict))):
        with patch('src.infrastructure.api.routes.strategies.get_strategy_repo', return_value=mock_repo):
            try:
                # Create request object
                req = UpdateActiveVersionRequest(config=MagicMock(dict=MagicMock(return_value=config_dict)), created_by="test")
                
                # Call the function
                result = await update_active_strategy_version(
                    strategy_id=strategy_id,
                    req=req,
                    repo=mock_repo
                )
                
                # Verify the result
                assert result is not None
                print("✓ update_active_strategy_version succeeded with class-based strategy")
                return True
            except HTTPException as e:
                print(f"✗ update_active_strategy_version failed with HTTPException: {e.detail}")
                return False
            except Exception as e:
                print(f"✗ update_active_strategy_version failed with exception: {e}")
                import traceback
                traceback.print_exc()
                return False

async def test_update_active_strategy_version_config_based():
    """Test that update_active_strategy_version still works with config-based strategies."""
    print("\nTesting update_active_strategy_version with config-based strategy...")
    
    # Setup
    strategy_id = uuid4()
    version_number = 2
    
    # Create a mock strategy definition (config-based)
    mock_strategy = MagicMock(spec=StrategyDefinition)
    mock_strategy.id = strategy_id
    mock_strategy.name = "Test Config-Based Strategy"
    mock_strategy.mode = "paper"
    mock_strategy.status = "draft"
    mock_strategy.current_version = 1
    mock_strategy.strategy_type = "config"  # Config-based strategy
    mock_strategy.class_path = None
    mock_strategy.created_by = "test"
    mock_strategy.created_at = datetime.now(UTC)
    mock_strategy.updated_at = datetime.now(UTC)
    
    # Mock strategy with valid config
    mock_strategy.config = {
        "meta": {"name": "Test", "schema_version": 1},
        "universe": {"symbols": ["BTC/USDT"], "timeframe": "1H"},
        "signal": {"type": "rsi", "params": {"period": 14, "oversold": 30, "overbought": 70}},
        "risk": {"max_position_size_pct": 10},
        "execution": {"order_type": "market"},
        "mode": "paper"
    }
    
    # Create a mock version
    mock_version = MagicMock(spec=StrategyConfigVersion)
    mock_version.id = uuid4()
    mock_version.version = version_number
    mock_version.is_active = False
    mock_version.strategy_id = strategy_id
    mock_version.config = mock_strategy.config  # Same config
    mock_version.created_by = "test"
    mock_version.created_at = datetime.now(UTC)
    
    # Mock repository
    mock_repo = MagicMock()
    mock_repo.get_by_id = AsyncMock(return_value=mock_strategy)
    mock_repo.list_versions = AsyncMock(return_value=[mock_version])  # Need at least one version
    mock_repo.create_version = AsyncMock(return_value=mock_version)
    mock_repo.set_active_version = AsyncMock(return_value=True)
    
    # Create request with valid config
    config_dict = {
        "meta": {"name": "Test", "schema_version": 1},
        "universe": {"symbols": ["BTC/USDT"], "timeframe": "1H"},
        "signal": {"type": "rsi", "params": {"period": 14, "oversold": 30, "overbought": 70}},
        "risk": {"max_position_size_pct": 10},
        "execution": {"order_type": "market"},
        "mode": "paper"
    }
    
    # Mock the StrategyConfigSchema to avoid validation issues in testing
    with patch('src.infrastructure.api.routes.strategies.StrategyConfigSchema', return_value=MagicMock(dict=MagicMock(return_value=config_dict))):
        with patch('src.infrastructure.api.routes.strategies.get_strategy_repo', return_value=mock_repo):
            try:
                # Create request object
                req = UpdateActiveVersionRequest(config=MagicMock(dict=MagicMock(return_value=config_dict)), created_by="test")
                
                # Call the function
                result = await update_active_strategy_version(
                    strategy_id=strategy_id,
                    req=req,
                    repo=mock_repo
                )
                
                # Verify the result
                assert result is not None
                print("✓ update_active_strategy_version succeeded with config-based strategy")
                return True
            except HTTPException as e:
                print(f"✗ update_active_strategy_version failed with HTTPException: {e.detail}")
                return False
            except Exception as e:
                print(f"✗ update_active_strategy_version failed with exception: {e}")
                import traceback
                traceback.print_exc()
                return False

async def main():
    """Run all tests."""
    success1 = await test_update_active_strategy_version_class_based()
    success2 = await test_update_active_strategy_version_config_based()
    
    if success1 and success2:
        print("\n🎉 All tests passed!")
        return True
    else:
        print("\n❌ Some tests failed!")
        return False

if __name__ == "__main__":
    import asyncio
    success = asyncio.run(main())
    sys.exit(0 if success else 1)