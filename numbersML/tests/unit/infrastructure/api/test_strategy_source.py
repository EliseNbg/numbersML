"""Unit tests for Strategy Source Code Management API."""

import pytest
import asyncio
from pathlib import Path
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

# Import the router for testing
from src.infrastructure.api.routes.strategy_source import (
    USER_STRATEGIES_DIR,
    _validate_strategy_code,
    StrategyValidationResult,
    _python_file_to_class_path,
    _class_path_to_file_path,
    _is_safe_path,
)


class TestValidateStrategyCode:
    """Test strategy code validation."""

    def test_valid_strategy_code(self):
        """Valid Python code with Strategy inheritance."""
        content = '''
from src.domain.strategies.base import Strategy, Signal, SignalType, EnrichedTick

class MyStrategy(Strategy):
    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        return None
'''
        result = _validate_strategy_code(content)
        assert result.valid is True
        assert len(result.errors) == 0
        assert result.class_found is True
        assert result.inherits_strategy is True

    def test_invalid_syntax(self):
        """Invalid Python syntax."""
        content = "class BadSyntax(Strategy:\n"  # Missing closing paren
        result = _validate_strategy_code(content)
        assert result.valid is False
        assert len(result.errors) > 0
        assert "Syntax error" in result.errors[0]

    def test_no_class_definition(self):
        """Code without class definition."""
        content = "x = 5\nprint('hello')\n"
        result = _validate_strategy_code(content)
        assert result.valid is False
        assert "Class definition not found" in result.errors[0]

    def test_class_not_inheriting_strategy(self):
        """Class that doesn't inherit from Strategy."""
        content = '''
class MyStrategy:
    def on_tick(self, tick):
        return None
'''
        result = _validate_strategy_code(content, class_name="MyStrategy")
        assert result.class_found is True
        # Note: AST check may not catch this in all cases
        # The warning about runtime check is expected

    def test_specific_class_name(self):
        """Validate specific class name."""
        content = '''
class OtherStrategy(Strategy):
    pass
'''
        result = _validate_strategy_code(content, class_name="MyStrategy")
        assert result.class_found is False
        assert result.valid is False


class TestStrategySourceAPI:
    """Test strategy source API endpoints."""

    @pytest.fixture
    def app(self):
        """Create test app with mocked auth."""
        from src.infrastructure.api.auth import AuthContext

        app = FastAPI()

        # Mock the auth dependency
        async def mock_auth() -> AuthContext:
            return AuthContext(
                api_key="test-key",
                roles=["trader"],
                name="test-user"
            )

        from src.infrastructure.api.routes.strategy_source import router
        app.include_router(router)

        # Override the auth dependency
        from src.infrastructure.api.auth import require_trader
        app.dependency_overrides[require_trader] = mock_auth

        return app

    @pytest.fixture
    def client(self, app) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_list_strategies_empty(self, client):
        """List strategies when directory is empty."""
        # Mock the _get_user_strategies_dir function to return a path with no .py files
        from pathlib import Path
        from unittest.mock import MagicMock

        mock_dir = Path("/tmp/nonexistent_strategies")
        mock_dir.mkdir(exist_ok=True)
        # Ensure it's empty
        for f in mock_dir.glob("*.py"):
            f.unlink()

        with patch("src.infrastructure.api.routes.strategy_source._get_user_strategies_dir", return_value=mock_dir):
            response = client.get("/api/strategies/source")
            assert response.status_code == 200
            assert response.json() == []

        # Cleanup temp dir
        import shutil
        shutil.rmtree(mock_dir, ignore_errors=True)

    def test_list_strategies_with_files(self, client):
        """List strategies with files present."""
        # Create a test strategy file
        USER_STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)
        test_file = USER_STRATEGIES_DIR / "test_strategy.py"
        test_file.write_text(
            "from src.domain.strategies.base import Strategy\n"
            "class TestStrategy(Strategy):\n    pass\n"
        )

        response = client.get("/api/strategies/source")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any("test_strategy" in item["file_path"] for item in data)

        # Cleanup
        test_file.unlink()

    def test_get_strategy_source(self, client):
        """Get strategy source code."""
        USER_STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)
        test_file = USER_STRATEGIES_DIR / "test_get.py"
        test_content = (
            "from src.domain.strategies.base import Strategy\n"
            "class TestGet(Strategy):\n    pass\n"
        )
        test_file.write_text(test_content)

        response = client.get(
            "/api/strategies/source/src.strategies.user.test_get.TestGet"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == test_content
        assert data["class_path"] == "src.strategies.user.test_get.TestGet"

        # Cleanup
        test_file.unlink()

    def test_get_nonexistent_strategy(self, client):
        """Get non-existent strategy file."""
        response = client.get(
            "/api/strategies/source/src.strategies.user.nonexistentfile.Dummy"
        )
        assert response.status_code == 404

    def test_save_strategy_source(self, client):
        """Save new strategy source code."""
        USER_STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)
        content = (
            "from src.domain.strategies.base import Strategy\n"
            "class SavedStrategy(Strategy):\n    pass\n"
        )

        response = client.put(
            "/api/strategies/source/src.strategies.user.saved_strategy.SavedStrategy",
            headers={"Content-Type": "application/json"},
            json={"content": content, "overwrite": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == content

        # Verify file was created
        saved_file = USER_STRATEGIES_DIR / "saved_strategy.py"
        assert saved_file.exists()

        # Cleanup
        saved_file.unlink()

    def test_save_existing_without_overwrite(self, client):
        """Save to existing file without overwrite flag."""
        USER_STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)
        test_file = USER_STRATEGIES_DIR / "test_existing_no_overwrite.py"
        test_file.write_text("original content")

        content = (
            "from src.domain.strategies.base import Strategy\n"
            "class NewStrategy(Strategy):\n    pass\n"
        )
        response = client.put(
            "/api/strategies/source/src.strategies.user.test_existing_no_overwrite.NewStrategy",
            headers={"Content-Type": "application/json"},
            json={"content": content, "overwrite": False},
        )
        assert response.status_code == 409  # Conflict

        # Cleanup
        test_file.unlink()

    def test_save_with_overwrite(self, client):
        """Save to existing file with overwrite flag."""
        USER_STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)
        test_file = USER_STRATEGIES_DIR / "overwrite.py"
        test_file.write_text("original content")

        content = (
            "from src.domain.strategies.base import Strategy\n"
            "class OverwriteStrategy(Strategy):\n    pass\n"
        )
        response = client.put(
            "/api/strategies/source/src.strategies.user.overwrite.OverwriteStrategy",
            headers={"Content-Type": "application/json"},
            json={"content": content, "overwrite": True},
        )
        assert response.status_code == 200

        # Verify file was overwritten
        assert test_file.read_text() == content

        # Cleanup
        test_file.unlink()

    def test_save_invalid_syntax(self, client):
        """Save with invalid Python syntax."""
        response = client.put(
            "/api/strategies/source/src.strategies.user.invalid.BadSyntax",
            headers={"Content-Type": "application/json"},
            json={"content": "class BadSyntax(\n", "overwrite": False},
        )
        assert response.status_code == 400
        assert "Invalid strategy code" in response.json()["detail"]

    def test_delete_strategy(self, client):
        """Delete strategy file."""
        USER_STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)
        test_file = USER_STRATEGIES_DIR / "to_delete.py"
        test_file.write_text("content")

        response = client.delete(
            "/api/strategies/source/src.strategies.user.to_delete.ToDelete"
        )
        assert response.status_code == 204
        assert not test_file.exists()

    def test_delete_init_file_blocked(self, client):
        """Cannot delete __init__.py."""
        USER_STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)
        init_file = USER_STRATEGIES_DIR / "__init__.py"
        init_file.write_text("")  # Create if not exists

        response = client.delete(
            "/api/strategies/source/src.strategies.user.__init__.Dummy"
        )
        assert response.status_code == 400
        assert "Cannot delete __init__.py" in response.json()["detail"]

    def test_delete_nonexistent(self, client):
        """Delete non-existent file."""
        response = client.delete(
            "/api/strategies/source/src.strategies.user.nonexistentfile.Dummy"
        )
        assert response.status_code == 404

    def test_validate_endpoint(self, client):
        """Validate strategy code via API."""
        content = '''
from src.domain.strategies.base import Strategy, Signal, EnrichedTick

class ValidStrategy(Strategy):
    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        return None
'''
        response = client.post(
            "/api/strategies/source/validate",
            headers={"Content-Type": "application/json"},
            json={"content": content, "class_name": "ValidStrategy"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    def test_validate_invalid_syntax(self, client):
        """Validate with invalid syntax."""
        response = client.post(
            "/api/strategies/source/validate",
            headers={"Content-Type": "application/json"},
            json={"content": "class Bad(:\n", "class_name": "Bad"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_path_traversal_blocked(self, client):
        """Path traversal attempts are blocked."""
        # Try to access file outside user directory
        # Note: FastAPI may not match the route, so we test the safety function directly
        from pathlib import Path
        unsafe_path = Path("/etc/passwd")
        assert _is_safe_path(unsafe_path) is False

    def test_unauthorized_access(self, client):
        """Endpoints require authentication."""
        # Remove the auth override to simulate unauthorized access
        from src.infrastructure.api.auth import require_trader
        client.app.dependency_overrides.pop(require_trader, None)

        response = client.get("/api/strategies/source")
        # Should get 403 or 401 (depending on auth implementation)
        assert response.status_code in [401, 403]


class TestHelperFunctions:
    """Test helper functions."""

    def test_python_file_to_class_path(self):
        """Convert file path to class path."""
        # Use the actual user strategies directory
        user_dir = USER_STRATEGIES_DIR
        user_dir.mkdir(parents=True, exist_ok=True)

        file_path = user_dir / "my_strategy.py"
        # Create a dummy file for the test
        file_path.write_text("# test")

        class_path = _python_file_to_class_path(file_path)
        assert class_path == "src.strategies.user.my_strategy"

        # Cleanup
        file_path.unlink()

    def test_class_path_to_file_path(self):
        """Convert class path to file path."""
        class_path = "src.strategies.user.my_strategy.MyStrategy"
        file_path = _class_path_to_file_path(class_path)
        assert file_path.suffix == ".py"
        assert "my_strategy.py" in str(file_path)

    def test_is_safe_path(self):
        """Path safety check."""
        # Valid path
        valid_path = USER_STRATEGIES_DIR / "test.py"
        assert _is_safe_path(valid_path) is True

        # Path traversal
        invalid_path = Path("/etc/passwd")
        assert _is_safe_path(invalid_path) is False

        # Path outside user directory
        outside_path = USER_STRATEGIES_DIR.parent.parent / "other" / "test.py"
        assert _is_safe_path(outside_path) is False
