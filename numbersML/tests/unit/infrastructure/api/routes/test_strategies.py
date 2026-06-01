"""Unit tests for strategy API endpoints."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from src.domain.strategies.strategy_config import StrategyDefinition


def create_mock_pool(connection: AsyncMock) -> MagicMock:
    """Create a mock pool whose acquire() returns an async context manager yielding the given connection."""
    pool = MagicMock()

    @asynccontextmanager
    async def _acquire():
        yield connection

    pool.acquire = MagicMock(side_effect=_acquire)
    return pool


@pytest.fixture
def mock_connection() -> AsyncMock:
    """Build a mocked asyncpg connection."""
    conn = AsyncMock()
    # Set up the transaction method to return an async context manager
    mock_transaction_context = AsyncMock()
    mock_transaction_context.__aenter__ = AsyncMock(return_value=None)
    mock_transaction_context.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=mock_transaction_context)
    return conn


@pytest.fixture
def mock_pool(mock_connection: AsyncMock) -> MagicMock:
    """Build a mocked asyncpg pool that yields the mock connection."""
    return create_mock_pool(mock_connection)


@pytest.fixture
def auth_headers():
    """Mock authentication headers."""
    return {"Authorization": "Bearer test-token"}


class TestUpdateActiveVersion:
    """Test updating active strategy version endpoint."""

    @pytest.mark.asyncio
    async def test_update_active_version_success(
        self, mock_pool: MagicMock, mock_connection: AsyncMock, auth_headers
    ):
        """Test successfully updating active strategy version."""
        from src.infrastructure.api.app import app
        from src.infrastructure.database import set_db_pool

        strategy_id = uuid4()
        now = datetime.now(UTC)

        # Mock strategy row
        strategy_row = {
            "id": strategy_id,
            "name": "Test Strategy",
            "description": "Test strategy for version update",
            "mode": "paper",
            "status": "draft",
            "current_version": 1,
            "created_by": "system",
            "created_at": now,
            "updated_at": now,
        }

        # Initial version row
        initial_version_row = {
            "strategy_id": strategy_id,
            "version": 1,
            "schema_version": 1,
            "config": {
                "meta": {"name": "Test Strategy", "schema_version": 1},
                "universe": {"symbols": ["BTC/USDC"], "timeframe": "1M"},
                "signal": {
                    "type": "rsi",
                    "params": {"period": 14, "overbought": 70, "oversold": 30},
                },
                "risk": {
                    "max_position_size_pct": 10,
                    "max_daily_loss_pct": 5,
                    "stop_loss_pct": 2,
                    "take_profit_pct": 5,
                },
                "execution": {
                    "order_type": "market",
                    "slippage_bps": 10,  # 0.1% in bps
                    "fee_bps": 5,  # 0.05% in bps
                },
                "mode": "paper",
                "status": "draft",
            },
            "is_active": True,
            "created_by": "system",
            "created_at": now,
        }

        # New version row (what will be created)
        new_version_row = {
            "strategy_id": strategy_id,
            "version": 2,
            "schema_version": 1,
            "config": {
                "meta": {"name": "Test Strategy", "schema_version": 1},
                "universe": {"symbols": ["ETH/USDC"], "timeframe": "1M"},  # Changed symbol
                "signal": {
                    "type": "rsi",
                    "params": {"period": 14, "overbought": 70, "oversold": 30},
                },
                "risk": {
                    "max_position_size_pct": 10,
                    "max_daily_loss_pct": 5,
                    "stop_loss_pct": 2,
                    "take_profit_pct": 5,
                },
                "execution": {
                    "order_type": "market",
                    "slippage_bps": 10,  # 0.1% in bps
                    "fee_bps": 5,  # 0.05% in bps
                },
                "mode": "paper",
                "status": "draft",
            },
            "is_active": True,
            "created_by": "test-user",
            "created_at": now,
        }

        # Mock fetchrow calls:
        # 1. get_by_id for existence check in update_active_strategy_version (endpoint)
        # 2. SELECT FOR UPDATE inside create_version to lock strategy row
        # 3. MAX(version) query inside create_version
        # 4. INSERT returning row in create_version
        # 5. set_active_version: fetchrow to check version exists (returns id)
        version_id = uuid4()
        inserted_version_row = {
            "id": version_id,
            "strategy_id": strategy_id,
            "version": 2,
            "schema_version": 1,
            "config": new_version_row["config"],  # dict, asyncpg returns dict for JSONB
            "is_active": False,  # initially not active
            "created_by": "test-user",
            "created_at": now,
        }
        mock_connection.fetchrow.side_effect = [
            strategy_row,  # 1. get_by_id for existence check
            strategy_row,  # 2. SELECT FOR UPDATE (lock, result unused)
            {"max_ver": 1},  # 3. MAX(version) query -> current max is 1
            inserted_version_row,  # 4. INSERT returning row
            {"id": version_id},  # 5. set_active_version SELECT id
        ]
        # Mock fetch for list_versions calls (first call in POST, second call in GET)
        mock_connection.fetch.side_effect = [
            [initial_version_row],  # First list_versions call (before update)
            [new_version_row],  # Second list_versions call after activation
        ]

        set_db_pool(mock_pool)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Update active version
            update_data = {
                "config": {
                    "meta": {"name": "Test Strategy", "schema_version": 1},
                    "universe": {"symbols": ["ETH/USDC"], "timeframe": "1M"},
                    "signal": {
                        "type": "rsi",
                        "params": {"period": 14, "overbought": 70, "oversold": 30},
                    },
                    "risk": {
                        "max_position_size_pct": 10,
                        "max_daily_loss_pct": 5,
                        "stop_loss_pct": 2,
                        "take_profit_pct": 5,
                    },
                    "execution": {
                        "order_type": "market",
                        "slippage_bps": 10,  # 0.1% in bps
                        "fee_bps": 5,  # 0.05% in bps
                    },
                    "mode": "paper",
                    "status": "draft",
                },
                "created_by": "test-user",
            }

            update_resp = await client.post(
                f"/api/strategies/{strategy_id}/active-version",
                json=update_data,
                headers=auth_headers,
            )

            assert update_resp.status_code == 200
            new_version = update_resp.json()

            # Verify new version is active
            assert new_version["is_active"] == True
            assert new_version["version"] == 2
            assert new_version["config"]["universe"]["symbols"] == ["ETH/USDC"]

            # Verify old version is no longer active (by checking list_versions)
            versions_resp = await client.get(
                f"/api/strategies/{strategy_id}/versions", headers=auth_headers
            )
            assert versions_resp.status_code == 200
            versions_after = versions_resp.json()
            active_after = [v for v in versions_after if v["is_active"]][0]
            assert active_after["version"] == new_version["version"]

        set_db_pool(None)  # Clean up

    @pytest.mark.asyncio
    async def test_update_active_version_validation_error(
        self, mock_pool: MagicMock, mock_connection: AsyncMock, auth_headers
    ):
        """Test validation error when updating with invalid config."""
        from src.infrastructure.api.app import app
        from src.infrastructure.database import set_db_pool

        strategy_id = uuid4()
        now = datetime.now(UTC)

        # Mock strategy row
        strategy_row = {
            "id": strategy_id,
            "name": "Test Strategy",
            "description": "Test strategy for validation",
            "mode": "paper",
            "status": "draft",
            "current_version": 1,
            "created_by": "system",
            "created_at": now,
            "updated_at": now,
        }

        # Initial version row
        initial_version_row = {
            "strategy_id": strategy_id,
            "version": 1,
            "schema_version": 1,
            "config": {
                "meta": {"name": "Test Strategy", "schema_version": 1},
                "universe": {"symbols": ["BTC/USDC"], "timeframe": "1M"},
                "signal": {
                    "type": "rsi",
                    "params": {"period": 14, "overbought": 70, "oversold": 30},
                },
                "risk": {
                    "max_position_size_pct": 10,
                    "max_daily_loss_pct": 5,
                    "stop_loss_pct": 2,
                    "take_profit_pct": 5,
                },
                "execution": {
                    "order_type": "market",
                    "slippage_bps": 10,  # 0.1% in bps
                    "fee_bps": 5,  # 0.05% in bps
                },
                "mode": "paper",
                "status": "draft",
            },
            "is_active": True,
            "created_by": "system",
            "created_at": now,
        }

        # Initial version row
        initial_version_row = {
            "strategy_id": strategy_id,
            "version": 1,
            "schema_version": 1,
            "config": {
                "meta": {"name": "Test Strategy", "schema_version": 1},
                "universe": {"symbols": ["BTC/USDC"], "timeframe": "1M"},
                "signal": {
                    "type": "rsi",
                    "params": {"period": 14, "overbought": 70, "oversold": 30},
                },
                "risk": {
                    "max_position_size_pct": 10,
                    "max_daily_loss_pct": 5,
                    "stop_loss_pct": 2,
                    "take_profit_pct": 5,
                },
                "execution": {"order_type": "market", "slippage_tolerance_pct": 0.1},
                "mode": "paper",
                "status": "draft",
            },
            "is_active": True,
            "created_by": "system",
            "created_at": now,
        }

        mock_connection.fetchrow.return_value = strategy_row
        mock_connection.fetch.return_value = [initial_version_row]

        set_db_pool(mock_pool)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Try to update with invalid config (missing required universe symbols)
            invalid_config = {
                "meta": {"name": "Test Strategy", "schema_version": 1},
                "universe": {},  # Missing symbols and timeframe - should cause validation error
                "signal": {
                    "type": "rsi",
                    "params": {"period": 14, "overbought": 70, "oversold": 30},
                },
                "risk": {
                    "max_position_size_pct": 10,
                    "max_daily_loss_pct": 5,
                    "stop_loss_pct": 2,
                    "take_profit_pct": 5,
                },
                "execution": {
                    "order_type": "market",
                    "slippage_bps": 10,  # 0.1% in bps
                    "fee_bps": 5,  # 0.05% in bps
                },
                "mode": "paper",
                "status": "draft",
            }

            update_data = {
                "config": invalid_config,
                "created_by": "test-user",
            }

            update_resp = await client.post(
                f"/api/strategies/{strategy_id}/active-version",
                json=update_data,
                headers=auth_headers,
            )

            assert update_resp.status_code == 400
            assert "validation_issues" in update_resp.json()["detail"]

        set_db_pool(None)  # Clean up

    @pytest.mark.asyncio
    async def test_update_active_version_not_found(
        self, mock_pool: MagicMock, mock_connection: AsyncMock, auth_headers
    ):
        """Test updating non-existent strategy."""
        from src.infrastructure.api.app import app
        from src.infrastructure.database import set_db_pool

        fake_id = uuid4()
        mock_connection.fetchrow.return_value = None  # Strategy not found

        set_db_pool(mock_pool)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            update_data = {
                "config": {
                    "meta": {"name": "Test Strategy", "schema_version": 1},
                    "universe": {"symbols": ["BTC/USDC"], "timeframe": "1M"},
                    "signal": {
                        "type": "rsi",
                        "params": {"period": 14, "overbought": 70, "oversold": 30},
                    },
                    "risk": {
                        "max_position_size_pct": 10,
                        "max_daily_loss_pct": 5,
                        "stop_loss_pct": 2,
                        "take_profit_pct": 5,
                    },
                    "execution": {
                        "order_type": "market",
                        "slippage_bps": 10,  # 0.1% in bps
                        "fee_bps": 5,  # 0.05% in bps
                    },
                    "mode": "paper",
                    "status": "draft",
                },
                "created_by": "test-user",
            }

            update_resp = await client.post(
                f"/api/strategies/{fake_id}/active-version",
                json=update_data,
                headers=auth_headers,
            )

            assert update_resp.status_code == 404

        set_db_pool(None)  # Clean up


class TestUpdateStrategyMode:
    """Test toggling strategy mode between paper and live."""

    @pytest.mark.asyncio
    async def test_toggle_from_paper_to_live(
        self, mock_pool: MagicMock, mock_connection: AsyncMock, auth_headers
    ):
        """Test switching strategy mode from paper to live."""
        from src.infrastructure.api.app import app
        from src.infrastructure.database import set_db_pool

        strategy_id = uuid4()
        now = datetime.now(UTC)

        # Mock strategy row
        strategy_row = {
            "id": strategy_id,
            "name": "Test Strategy",
            "description": "Test strategy for mode toggle",
            "mode": "paper",
            "status": "draft",
            "current_version": 1,
            "created_by": "system",
            "created_at": now,
            "updated_at": now,
        }

        # Updated strategy row (after mode change)
        updated_strategy_row = {
            "id": strategy_id,
            "name": "Test Strategy",
            "description": "Test strategy for mode toggle",
            "mode": "live",
            "status": "draft",
            "current_version": 2,
            "created_by": "system",
            "created_at": now,
            "updated_at": now,
        }

        # Version row
        version_row = {
            "strategy_id": strategy_id,
            "version": 1,
            "schema_version": 1,
            "config": {
                "meta": {"name": "Test Strategy", "schema_version": 1},
                "universe": {"symbols": ["BTC/USDC"], "timeframe": "1M"},
                "signal": {"type": "rsi", "params": {"period": 14, "overbought": 70, "oversold": 30}},
                "risk": {"max_position_size_pct": 10, "max_daily_loss_pct": 5, "stop_loss_pct": 2, "take_profit_pct": 5},
                "execution": {"order_type": "market", "slippage_bps": 10, "fee_bps": 5},
                "mode": "paper",
                "status": "draft",
            },
            "is_active": True,
            "created_by": "system",
            "created_at": now,
        }

        mock_connection.fetchrow.side_effect = [
            strategy_row,  # get_by_id (check exists)
            updated_strategy_row,  # save (INSERT ... RETURNING)
            strategy_row,  # get_by_id (inside create_version FOR UPDATE)
            {"max_ver": 1},  # MAX(version)
            {"id": uuid4(), "strategy_id": strategy_id, "version": 2, "schema_version": 1,
             "config": {}, "is_active": True, "created_by": "api", "created_at": now},  # INSERT RETURNING
            {"id": uuid4()},  # set_active_version: SELECT target version
        ]
        mock_connection.fetch.side_effect = [
            [version_row],  # list_versions
        ]

        set_db_pool(mock_pool)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/strategies/{strategy_id}/mode",
                json={"mode": "live"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["mode"] == "live"

        set_db_pool(None)

    @pytest.mark.asyncio
    async def test_toggle_same_mode_returns_400(
        self, mock_pool: MagicMock, mock_connection: AsyncMock, auth_headers
    ):
        """Test that toggling to the same mode returns 400."""
        from src.infrastructure.api.app import app
        from src.infrastructure.database import set_db_pool

        strategy_id = uuid4()
        now = datetime.now(UTC)

        strategy_row = {
            "id": strategy_id,
            "name": "Test Strategy",
            "description": "Test strategy",
            "mode": "paper",
            "status": "draft",
            "current_version": 1,
            "created_by": "system",
            "created_at": now,
            "updated_at": now,
        }

        mock_connection.fetchrow.return_value = strategy_row

        set_db_pool(mock_pool)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/strategies/{strategy_id}/mode",
                json={"mode": "paper"},
                headers=auth_headers,
            )
            assert resp.status_code == 400
            assert "already" in resp.json()["detail"]

        set_db_pool(None)

    @pytest.mark.asyncio
    async def test_toggle_mode_not_found(
        self, mock_pool: MagicMock, mock_connection: AsyncMock, auth_headers
    ):
        """Test toggling mode on non-existent strategy returns 404."""
        from src.infrastructure.api.app import app
        from src.infrastructure.database import set_db_pool

        fake_id = uuid4()
        mock_connection.fetchrow.return_value = None

        set_db_pool(mock_pool)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/strategies/{fake_id}/mode",
                json={"mode": "live"},
                headers=auth_headers,
            )
            assert resp.status_code == 404

        set_db_pool(None)

    @pytest.mark.asyncio
    async def test_toggle_mode_invalid_payload(
        self, mock_pool: MagicMock, mock_connection: AsyncMock, auth_headers
    ):
        """Test that invalid mode value returns 422."""
        from src.infrastructure.api.app import app
        from src.infrastructure.database import set_db_pool

        strategy_id = uuid4()
        set_db_pool(mock_pool)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/strategies/{strategy_id}/mode",
                json={"mode": "invalid"},
                headers=auth_headers,
            )
            assert resp.status_code == 422

        set_db_pool(None)
