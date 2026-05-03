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

    def test_routes_registered(self, client: TestClient) -> None:
        """Test that routes are registered."""
        routes = [route.path for route in client.app.routes]

        assert "/api/backup/create" in routes
        assert "/api/backup/list" in routes
        assert "/api/backup/details/{backup_name}" in routes
        assert "/api/backup/restore/{backup_name}" in routes
        assert "/api/backup/download/{backup_name}" in routes
        assert "/api/backup/upload" in routes
        assert "/api/backup/delete/{backup_name}" in routes

    @patch("src.infrastructure.api.routes.backup.BackupService")
    def test_create_backup(self, mock_service_class, client: TestClient) -> None:
        """Test backup creation endpoint."""
        mock_service = AsyncMock()
        mock_service.create_backup.return_value = {
            "name": "backup_20260501_120000.sql.gz",
            "path": "/path/to/backup_20260501_120000.sql.gz",
            "size": 1024,
            "created_at": "2026-05-01T12:00:00",
        }
        mock_service_class.return_value = mock_service

        response = client.post("/api/backup/create")

        assert response.status_code == 200
        data = response.json()
        assert "backup_20260501_120000.sql.gz" in data["name"]
        assert data["size"] == 1024

    @patch("src.infrastructure.api.routes.backup.BackupService")
    def test_create_backup_with_compress(self, mock_service_class, client: TestClient) -> None:
        """Test backup creation with compress parameter."""
        mock_service = AsyncMock()
        mock_service.create_backup.return_value = {
            "name": "backup_20260501_120000.sql.gz",
            "path": "/path/to/backup_20260501_120000.sql.gz",
            "size": 1024,
            "created_at": "2026-05-01T12:00:00",
        }
        mock_service_class.return_value = mock_service

        response = client.post("/api/backup/create?compress=false")

        assert response.status_code == 200
        mock_service.create_backup.assert_called_once_with(compress=False)

    @patch("src.infrastructure.api.routes.backup.BackupService")
    def test_list_backups(self, mock_service_class, client: TestClient) -> None:
        """Test list backups endpoint."""
        mock_service = AsyncMock()
        mock_service.list_backups.return_value = [
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
        mock_service_class.return_value = mock_service

        response = client.get("/api/backup/list")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "backup_20260501_120000.sql.gz"

    @patch("src.infrastructure.api.routes.backup.BackupService")
    def test_get_backup_details(self, mock_service_class, client: TestClient) -> None:
        """Test get backup details endpoint."""
        mock_service = AsyncMock()
        mock_service.get_backup_details.return_value = {
            "name": "backup_20260501_120000.sql.gz",
            "path": "/path/to/backup_20260501_120000.sql.gz",
            "size": 1024,
            "created_at": "2026-05-01T12:00:00",
        }
        mock_service_class.return_value = mock_service

        response = client.get("/api/backup/details/backup_20260501_120000.sql.gz")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "backup_20260501_120000.sql.gz"

    @patch("src.infrastructure.api.routes.backup.BackupService")
    def test_get_backup_details_not_found(self, mock_service_class, client: TestClient) -> None:
        """Test get backup details with non-existent backup."""
        mock_service = AsyncMock()
        mock_service.get_backup_details.side_effect = FileNotFoundError("Backup not found")
        mock_service_class.return_value = mock_service

        response = client.get("/api/backup/details/nonexistent.sql.gz")

        assert response.status_code == 404

    @patch("src.infrastructure.api.routes.backup.BackupService")
    def test_restore_backup(self, mock_service_class, client: TestClient) -> None:
        """Test restore backup endpoint."""
        mock_service = AsyncMock()
        mock_service.restore_backup.return_value = {
            "status": "success",
            "message": "Database restored from backup_20260501_120000.sql.gz",
        }
        mock_service_class.return_value = mock_service

        response = client.post("/api/backup/restore/backup_20260501_120000.sql.gz")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    @patch("src.infrastructure.api.routes.backup.BackupService")
    def test_restore_backup_not_found(self, mock_service_class, client: TestClient) -> None:
        """Test restore with non-existent backup."""
        mock_service = AsyncMock()
        mock_service.restore_backup.side_effect = FileNotFoundError("Backup not found")
        mock_service_class.return_value = mock_service

        response = client.post("/api/backup/restore/nonexistent.sql.gz")

        assert response.status_code == 404

    @patch("src.infrastructure.api.routes.backup.BackupService")
    def test_delete_backup(self, mock_service_class, client: TestClient) -> None:
        """Test delete backup endpoint."""
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.unlink") as mock_unlink,
        ):
            response = client.delete("/api/backup/delete/backup_20260501_120000.sql.gz")

            assert response.status_code == 200
            data = response.json()
            assert "deleted" in data["message"].lower()
            mock_unlink.assert_called_once()

    def test_delete_backup_not_found(self, client: TestClient) -> None:
        """Test delete with non-existent backup."""
        with patch("pathlib.Path.exists", return_value=False):
            response = client.delete("/api/backup/delete/nonexistent.sql.gz")

            assert response.status_code == 404

    def test_download_backup_not_found(self, client: TestClient) -> None:
        """Test download with non-existent backup."""
        with patch("pathlib.Path.exists", return_value=False):
            response = client.get("/api/backup/download/nonexistent.sql.gz")

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
