"""
Unit tests for backup API routes.

Tests:
    - Route registration
    - Endpoint responses
    - Error handling
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.api.routes.backup import get_backup_service
from src.infrastructure.api.routes.backup import router as backup_router


class TestBackupRoutes:
    """Test backup API routes."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app with backup routes."""
        app = FastAPI()
        app.include_router(backup_router)
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def mock_backup_service(self) -> AsyncMock:
        """Create a mock BackupService."""
        service = AsyncMock()
        return service

    @pytest.fixture
    def app_with_mocked_service(self, mock_backup_service: AsyncMock) -> FastAPI:
        """Create test app with backup service dependency overridden."""

        async def override_dependency():
            return mock_backup_service

        app = FastAPI()
        app.include_router(backup_router)
        app.dependency_overrides[get_backup_service] = override_dependency
        return app

    @pytest.fixture
    def client_with_mock(self, app_with_mocked_service: FastAPI) -> TestClient:
        """Create test client with mocked service."""
        return TestClient(app_with_mocked_service, raise_server_exceptions=False)

    def test_create_backup(
        self, client_with_mock: TestClient, mock_backup_service: AsyncMock
    ) -> None:
        """Test backup creation endpoint."""
        mock_backup_service.create_backup.return_value = {
            "name": "backup_20260501_120000.sql.gz",
            "path": "/path/to/backup_20260501_120000.sql.gz",
            "size": 1024,
            "created_at": "2026-05-01T12:00:00",
        }

        response = client_with_mock.post("/api/backup/create")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "backup_20260501_120000.sql.gz"
        assert data["size"] == 1024
        mock_backup_service.create_backup.assert_called_once_with(compress=True)

    def test_create_backup_with_compress(
        self, client_with_mock: TestClient, mock_backup_service: AsyncMock
    ) -> None:
        """Test backup creation with compress parameter."""
        mock_backup_service.create_backup.return_value = {
            "name": "backup_20260501_120000.sql.gz",
            "path": "/path/to/backup_20260501_120000.sql.gz",
            "size": 1024,
            "created_at": "2026-05-01T12:00:00",
        }

        response = client_with_mock.post("/api/backup/create?compress=false")

        assert response.status_code == 200
        mock_backup_service.create_backup.assert_called_once_with(compress=False)

    def test_list_backups(
        self, client_with_mock: TestClient, mock_backup_service: AsyncMock
    ) -> None:
        """Test list backups endpoint."""
        mock_backup_service.list_backups.return_value = [
            {
                "name": "backup_20260501_120000.sql.gz",
                "path": "/path/to/backup_20260501_120000.sql.gz",
                "size": 1024,
                "created_at": "2026-05-01T12:00:00",
            },
            {
                "name": "backup_20260430_120000.sql",
                "path": "/path/to/backup_20260430_120000.sql",
                "size": 2048,
                "created_at": "2026-04-30T12:00:00",
            },
        ]

        response = client_with_mock.get("/api/backup/list")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "backup_20260501_120000.sql.gz"

    def test_get_backup_details(
        self, client_with_mock: TestClient, mock_backup_service: AsyncMock
    ) -> None:
        """Test get backup details endpoint."""
        mock_backup_service.get_backup_details.return_value = {
            "name": "backup_20260501_120000.sql.gz",
            "path": "/path/to/backup_20260501_120000.sql.gz",
            "size": 1024,
            "created_at": "2026-05-01T12:00:00",
        }

        response = client_with_mock.get("/api/backup/details/backup_20260501_120000.sql.gz")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "backup_20260501_120000.sql.gz"

    def test_get_backup_details_not_found(
        self, client_with_mock: TestClient, mock_backup_service: AsyncMock
    ) -> None:
        """Test get backup details with non-existent backup."""
        mock_backup_service.get_backup_details.side_effect = FileNotFoundError("Backup not found")

        response = client_with_mock.get("/api/backup/details/nonexistent.sql.gz")

        assert response.status_code == 404

    def test_restore_backup(
        self, client_with_mock: TestClient, mock_backup_service: AsyncMock
    ) -> None:
        """Test restore backup endpoint."""
        mock_backup_service.restore_backup.return_value = {
            "status": "success",
            "message": "Database restored from backup_20260501_120000.sql.gz",
        }

        response = client_with_mock.post("/api/backup/restore/backup_20260501_120000.sql.gz")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_restore_backup_not_found(
        self, client_with_mock: TestClient, mock_backup_service: AsyncMock
    ) -> None:
        """Test restore with non-existent backup."""
        mock_backup_service.restore_backup.side_effect = FileNotFoundError("Backup not found")

        response = client_with_mock.post("/api/backup/restore/nonexistent.sql.gz")

        assert response.status_code == 404

    def test_delete_backup(self, client_with_mock: TestClient) -> None:
        """Test delete backup endpoint."""
        # For delete, we need to patch the filesystem operations
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.unlink") as mock_unlink,
        ):
            response = client_with_mock.delete("/api/backup/delete/backup_20260501_120000.sql.gz")

            assert response.status_code == 200
            data = response.json()
            assert "deleted" in data["message"].lower()
            mock_unlink.assert_called_once()

    def test_delete_backup_not_found(self, client_with_mock: TestClient) -> None:
        """Test delete with non-existent backup."""
        with patch("pathlib.Path.exists", return_value=False):
            response = client_with_mock.delete("/api/backup/delete/nonexistent.sql.gz")

            assert response.status_code == 404

    def test_download_backup_not_found(self, client_with_mock: TestClient) -> None:
        """Test download with non-existent backup."""
        with patch("pathlib.Path.exists", return_value=False):
            response = client_with_mock.get("/api/backup/download/nonexistent.sql.gz")

            assert response.status_code == 404


class TestBackupRoutesIntegration:
    """Integration tests for backup routes with full app."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app with all routes."""
        from src.infrastructure.api.app import create_app

        return create_app()

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_backup_routes_in_app(self, client: TestClient) -> None:
        """Test that backup routes are registered in the main app."""
        routes = [route.path for route in client.app.routes]

        assert "/api/backup/create" in routes
        assert "/api/backup/list" in routes
        assert "/api/backup/restore/{backup_name}" in routes
