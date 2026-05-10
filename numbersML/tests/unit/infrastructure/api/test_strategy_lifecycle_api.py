"""Unit tests for strategy lifecycle API dependencies."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI

from src.application.services.strategy_lifecycle import StrategyLifecycleService
from src.domain.strategies.base import Strategy
from src.domain.strategies.runtime import RuntimeState
from src.domain.strategies.strategy_config import StrategyConfigVersion, StrategyDefinition
from src.infrastructure.api.routes.strategies import get_lifecycle_service


class TestStrategyLifecycleApi:
    """Regression tests for API lifecycle state persistence."""

    @pytest.mark.asyncio
    async def test_get_lifecycle_service_reuses_app_scoped_instance(self) -> None:
        """Requests from the same app should share lifecycle runtime state."""
        app = FastAPI()
        request_one = SimpleNamespace(app=app)
        request_two = SimpleNamespace(app=app)

        strategy_id = uuid4()
        now = datetime.now(UTC)
        strategy_def = StrategyDefinition(
            id=strategy_id,
            name="Lifecycle API Test",
            description="Regression coverage for shared lifecycle service",
            mode="paper",
            status="draft",
            current_version=1,
            created_by="test",
            created_at=now,
            updated_at=now,
        )
        version = StrategyConfigVersion(
            strategy_id=strategy_id,
            version=1,
            schema_version=1,
            config={},
            is_active=True,
            created_by="test",
            created_at=now,
        )

        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = strategy_def
        mock_repo.list_versions.return_value = [version]

        mock_event_repo = AsyncMock()

        mock_strategy = AsyncMock(spec=Strategy)
        mock_strategy.id = str(strategy_id)

        with (
            patch(
                "src.infrastructure.api.routes.strategies.get_strategy_repo",
                AsyncMock(return_value=mock_repo),
            ),
            patch(
                "src.infrastructure.api.routes.strategies.get_event_repo",
                AsyncMock(return_value=mock_event_repo),
            ),
            patch.object(
                StrategyLifecycleService,
                "_load_strategy_instance",
                AsyncMock(return_value=mock_strategy),
            ),
        ):
            svc_one = await get_lifecycle_service(request_one)
            svc_two = await get_lifecycle_service(request_two)

            assert svc_one is svc_two

            activated = await svc_one.activate_strategy(strategy_id, version=1)
            assert activated is True

            runtime_state = await svc_two.get_runtime_state(strategy_id)
            assert runtime_state is not None
            assert runtime_state.state == RuntimeState.RUNNING

            deactivated = await svc_two.deactivate_strategy(strategy_id)
            assert deactivated is True

            final_runtime_state = await svc_one.get_runtime_state(strategy_id)
            assert final_runtime_state is not None
            assert final_runtime_state.state == RuntimeState.STOPPED
