"""
Backup and restore service.

Application service for managing database backups and restores.
"""

import logging
from pathlib import Path

from src.infrastructure.database.backup import (
    DEFAULT_BACKUP_DIR,
    get_backup_info,
)
from src.infrastructure.database.backup import (
    create_backup as create_backup_util,
)
from src.infrastructure.database.backup import (
    list_backups as list_backups_util,
)
from src.infrastructure.database.backup import (
    restore_backup as restore_backup_util,
)

logger = logging.getLogger(__name__)


class BackupService:
    """Service for database backup and restore operations."""

    def __init__(
        self,
        db_url: str,
        backup_dir: Path | None = None,
    ) -> None:
        """
        Initialize backup service.

        Args:
            db_url: Database connection URL.
            backup_dir: Directory to store backups.
        """
        self.db_url = db_url
        self.backup_dir = backup_dir or DEFAULT_BACKUP_DIR

    async def create_backup(self, compress: bool = True) -> dict:
        """
        Create a database backup.

        Args:
            compress: Whether to compress the backup.

        Returns:
            Dict with backup info: name, path, size, created_at.

        Raises:
            RuntimeError: If backup fails.
        """
        logger.info("Starting database backup...")

        try:
            backup_path = create_backup_util(
                db_url=self.db_url,
                backup_dir=self.backup_dir,
                compress=compress,
            )
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            raise RuntimeError(f"Backup failed: {e}") from e

        info = get_backup_info(backup_path)
        logger.info(f"Backup completed: {info['name']} ({info['size']} bytes)")
        return info

    async def restore_backup(self, backup_name: str) -> dict:
        """
        Restore database from backup.

        Args:
            backup_name: Name of backup file to restore.

        Returns:
            Dict with status message.

        Raises:
            FileNotFoundError: If backup file not found.
            RuntimeError: If restore fails.
        """
        backup_path = self.backup_dir / backup_name

        if not backup_path.exists():
            # Try with backups/ prefix
            backup_path = DEFAULT_BACKUP_DIR / backup_name
            if not backup_path.exists():
                raise FileNotFoundError(f"Backup not found: {backup_name}")

        logger.info(f"Starting database restore from {backup_name}...")

        try:
            restore_backup_util(
                backup_file=backup_path,
                db_url=self.db_url,
            )
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            raise RuntimeError(f"Restore failed: {e}") from e

        logger.info(f"Restore completed from {backup_name}")
        return {
            "status": "success",
            "message": f"Database restored from {backup_name}",
        }

    async def list_backups(self) -> list[dict]:
        """
        List available backups.

        Returns:
            List of backup info dicts.
        """
        try:
            backups = list_backups_util(backup_dir=self.backup_dir)
            return backups
        except Exception as e:
            logger.error(f"Failed to list backups: {e}")
            return []

    async def get_backup_details(self, backup_name: str) -> dict:
        """
        Get details of a specific backup.

        Args:
            backup_name: Name of backup file.

        Returns:
            Dict with backup info.

        Raises:
            FileNotFoundError: If backup not found.
        """
        backup_path = self.backup_dir / backup_name

        if not backup_path.exists():
            backup_path = DEFAULT_BACKUP_DIR / backup_name
            if not backup_path.exists():
                raise FileNotFoundError(f"Backup not found: {backup_name}")

        return get_backup_info(backup_path)
