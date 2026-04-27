"""
E2E Workflow Test: Complete Strategy Lifecycle

Tests the critical user journey:
1. Create strategy via API
2. Validate configuration
3. Activate in paper mode
4. Run backtest
5. Deactivate

This test validates the integration of all components in a realistic workflow.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any
from uuid import UUID, uuid4
from httpx import AsyncClient

from src.infrastructure.api.app import create_app
from src.application.services.strategy_lifecycle import StrategyLifecycleService
from src.application.services.strategy_runner import StrategyRunner
from src.domain.strategies.base import StrategyManager


@pytest.fixture
async def client():
    """Create test client."""
    app = create_app()
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_pool():
    """Database pool fixture."""
    import asyncpg
    pool = await asyncpg.create_pool(
        host="localhost",
        port=5432,
        user="test",
        password="test",
        database="test",
        min_size=1,
        max_size=5,
    )
    yield pool
    await pool.close()


@pytest.fixture
def strategy_manager():
    """Create strategy manager."""
    return StrategyManager()


class TestStrategyWorkflow:
    """
    E2E test for complete strategy lifecycle.
    
    This test simulates the full workflow a user would perform:
    - Create a new RSI strategy
    - Validate the configuration
    - Activate it in paper mode
    - Run a backtest
    - Deactivate when done
    """

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_complete_strategy_workflow(self, client, db_pool):
        """
        Test the complete strategy lifecycle workflow.
        
        Steps:
        1. Create strategy via API
        2. Validate configuration
        3. Activate in paper mode
        4. Run backtest
        5. Deactivate
        6. Verify final state
        """
        # ============================================================================
        # Step 1: Create Strategy
        # ============================================================================
        print("\n[Step 1] Creating strategy...")
        
        strategy_config = {
            "name": f"E2E_RSI_Strategy_{uuid4().hex[:8]}",
            "description": "E2E test RSI strategy",
            "type": "rsi",
            "symbols": ["BTC/USDC"],
            "timeframes": ["1m"],
            "config": {
                "period": 14,
                "oversold": 30,
                "overbought": 70,
                "order_size": 0.1,
                "max_position": 1.0,
            },
            "risk_limits": {
                "max_daily_loss": 100.0,
                "max_position_size": 1.0,
                "max_orders_per_hour": 10,
            },
        }
        
        response = await client.post("/api/v1/strategies", json=strategy_config)
        assert response.status_code == 201, f"Failed to create strategy: {response.text}"
        
        strategy_data = response.json()
        strategy_id = UUID(strategy_data["id"])
        
        print(f"  ✓ Strategy created: {strategy_id}")
        
        # ============================================================================
        # Step 2: Validate Configuration
        # ============================================================================
        print("\n[Step 2] Validating configuration...")
        
        response = await client.post(
            f"/api/v1/strategies/{strategy_id}/validate",
            json={}
        )
        assert response.status_code == 200, f"Validation failed: {response.text}"
        
        validation_result = response.json()
        assert validation_result["is_valid"] == True
        assert validation_result["errors"] == []
        
        print(f"  ✓ Configuration valid")
        
        # ============================================================================
        # Step 3: Activate in Paper Mode
        # ============================================================================
        print("\n[Step 3] Activating in paper mode...")
        
        response = await client.post(
            f"/api/v1/strategies/{strategy_id}/activate",
            json={"mode": "paper", "initial_balance": 10000.0}
        )
        assert response.status_code == 200, f"Activation failed: {response.text}"
        
        activation_result = response.json()
        assert activation_result["status"] == "active"
        assert activation_result["mode"] == "paper"
        
        print(f"  ✓ Strategy activated in paper mode")
        
        # ============================================================================
        # Step 4: Run Backtest
        # ============================================================================
        print("\n[Step 4] Running backtest...")
        
        backtest_request = {
            "strategy_id": str(strategy_id),
            "start_time": (datetime.utcnow() - timedelta(days=7)).isoformat(),
            "end_time": datetime.utcnow().isoformat(),
            "initial_balance": 10000.0,
            "fee_bps": 10,
            "slippage_bps": 5,
        }
        
        response = await client.post(
            "/api/v1/strategies/backtest",
            json=backtest_request
        )
        assert response.status_code == 202, f"Backtest submission failed: {response.text}"
        
        backtest_result = response.json()
        job_id = backtest_result["job_id"]
        
        print(f"  ✓ Backtest submitted: {job_id}")
        
        # Poll for completion
        max_polls = 30
        for i in range(max_polls):
            await asyncio.sleep(1)
            
            response = await client.get(f"/api/v1/strategies/backtest/{job_id}/status")
            status_data = response.json()
            
            if status_data["status"] in ["completed", "failed"]:
                break
        
        assert status_data["status"] == "completed", f"Backtest failed: {status_data}"
        
        # Verify backtest results
        response = await client.get(f"/api/v1/strategies/backtest/{job_id}/results")
        results_data = response.json()
        
        assert "metrics" in results_data
        assert "total_return" in results_data["metrics"]
        
        print(f"  ✓ Backtest completed")
        print(f"  ✓ Total return: {results_data['metrics']['total_return']:.2f}%")
        
        # ============================================================================
        # Step 5: Deactivate Strategy
        # ============================================================================
        print("\n[Step 5] Deactivating strategy...")
        
        response = await client.post(
            f"/api/v1/strategies/{strategy_id}/deactivate",
            json={}
        )
        assert response.status_code == 200, f"Deactivation failed: {response.text}"
        
        deactivation_result = response.json()
        assert deactivation_result["status"] == "inactive"
        
        print(f"  ✓ Strategy deactivated")
        
        # ============================================================================
        # Step 6: Verify Final State
        # ============================================================================
        print("\n[Step 6] Verifying final state...")
        
        response = await client.get(f"/api/v1/strategies/{strategy_id}")
        assert response.status_code == 200
        
        final_state = response.json()
        assert final_state["status"] == "inactive"
        assert final_state["lifecycle_state"] in ["inactive", "deactivated"]
        
        print(f"  ✓ Final state verified: {final_state['status']}")
        
        print("\n" + "=" * 60)
        print("E2E Workflow Test PASSED ✓")
        print("=" * 60)

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_strategy_validation_failure(self, client, db_pool):
        """
        Test that invalid strategy configurations are rejected.
        """
        print("\n[Test] Invalid configuration rejection...")
        
        invalid_config = {
            "name": "Invalid_Strategy",
            "description": "Test invalid config",
            "type": "rsi",
            "symbols": ["INVALID_SYMBOL"],  # Invalid symbol format
            "timeframes": ["1m"],
            "config": {
                "period": 200,  # Too long
                "oversold": 80,  # Higher than overbought
                "overbought": 20,  # Lower than oversold
                "order_size": -0.1,  # Negative size
            },
        }
        
        response = await client.post("/api/v1/strategies", json=invalid_config)
        
        # Should either fail creation or fail validation
        if response.status_code == 201:
            strategy_id = response.json()["id"]
            
            # Try to validate
            response = await client.post(
                f"/api/v1/strategies/{strategy_id}/validate",
                json={}
            )
            
            validation = response.json()
            assert validation["is_valid"] == False
            assert len(validation["errors"]) > 0
        else:
            # Creation should have been rejected
            assert response.status_code in [400, 422]
        
        print("  ✓ Invalid configuration properly rejected")

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_emergency_stop_workflow(self, client, db_pool):
        """
        Test emergency stop procedure during active strategy.
        """
        print("\n[Test] Emergency stop workflow...")
        
        # Create and activate a strategy
        strategy_config = {
            "name": f"Emergency_Test_{uuid4().hex[:8]}",
            "description": "Test emergency stop",
            "type": "rsi",
            "symbols": ["BTC/USDC"],
            "timeframes": ["1m"],
            "config": {
                "period": 14,
                "oversold": 30,
                "overbought": 70,
            },
        }
        
        response = await client.post("/api/v1/strategies", json=strategy_config)
        assert response.status_code == 201
        
        strategy_id = response.json()["id"]
        
        # Activate
        response = await client.post(
            f"/api/v1/strategies/{strategy_id}/activate",
            json={"mode": "paper"}
        )
        assert response.status_code == 200
        
        print("  ✓ Strategy activated")
        
        # Trigger emergency stop
        response = await client.post(
            "/api/v1/system/emergency-stop",
            json={
                "level": "strategy",
                "reason": "Test emergency stop",
                "strategy_id": strategy_id,
            }
        )
        assert response.status_code == 200
        
        print("  ✓ Emergency stop triggered")
        
        # Verify strategy is stopped
        response = await client.get(f"/api/v1/strategies/{strategy_id}/status")
        status_data = response.json()
        
        assert status_data.get("emergency_stopped") == True
        
        print("  ✓ Strategy confirmed stopped")
        
        # Release emergency stop
        response = await client.post(
            "/api/v1/system/emergency-stop/release",
            json={
                "reason": "Test complete",
            }
        )
        assert response.status_code == 200
        
        print("  ✓ Emergency stop released")
