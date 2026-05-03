"""
Database backup and restore utilities.

Provides functions to create and restore PostgreSQL database backups
using pg_dump and pg_restore.
"""

import logging
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Default backup directory
DEFAULT_BACKUP_DIR = Path("/home/andy/projects/numbers/numbersML/backups")


def ensure_backup_dir(backup_dir: Path | None = None) -> Path:
    """Ensure backup directory exists.

    Args:
        backup_dir: Backup directory path. Defaults to DEFAULT_BACKUP_DIR.

    Returns:
        Path to backup directory.
    """
    if backup_dir is None:
        backup_dir = DEFAULT_BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def create_backup(
    db_url: str,
    backup_dir: Path | None = None,
    compress: bool = True,
) -> Path:
    """Create a PostgreSQL database backup using pg_dump.

    Args:
        db_url: Database connection URL.
        backup_dir: Directory to store backups. Defaults to DEFAULT_BACKUP_DIR.
        compress: Whether to compress the backup with gzip.

    Returns:
        Path to the created backup file.

    Raises:
        RuntimeError: If pg_dump fails.
        FileNotFoundError: If pg_dump is not found.
    """
    backup_dir = ensure_backup_dir(backup_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if compress:
        backup_file = backup_dir / f"backup_{timestamp}.sql.gz"
        cmd = [
            "pg_dump",
            "--dbname",
            db_url,
            "--no-owner",
            "--no-acl",
            "--clean",
            "--if-exists",
            "--format=custom",
            "--compress=9",
        ]
    else:
        backup_file = backup_dir / f"backup_{timestamp}.sql"
        cmd = [
            "pg_dump",
            "--dbname",
            db_url,
            "--no-owner",
            "--no-acl",
            "--clean",
            "--if-exists",
        ]

    logger.info(f"Creating backup: {backup_file}")

    try:
        with open(backup_file, "wb") as f:
            subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.PIPE,
                check=True,
            )
    except FileNotFoundError as e:
        raise FileNotFoundError("pg_dump not found. Install postgresql-client.") from e
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        logger.error(f"pg_dump failed: {error_msg}")
        raise RuntimeError(f"Backup failed: {error_msg}") from e

    file_size = backup_file.stat().st_size
    logger.info(f"Backup created: {backup_file} ({file_size} bytes)")

    return backup_file


def restore_backup(
    backup_file: Path,
    db_url: str,
) -> None:
    """Restore a PostgreSQL database from backup.

    Args:
        backup_file: Path to backup file.
        db_url: Database connection URL.

    Raises:
        RuntimeError: If pg_restore fails.
        FileNotFoundError: If pg_restore is not found.
    """
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_file}")

    logger.info(f"Restoring backup: {backup_file}")

    # Determine format based on file extension
    if backup_file.suffix == ".gz" or backup_file.suffixes == [".sql", ".gz"]:
        cmd = [
            "pg_restore",
            "--dbname",
            db_url,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-acl",
            str(backup_file),
        ]
    else:
        # Plain SQL file
        cmd = ["psql", "--dbname", db_url, "--file", str(backup_file)]

    try:
        subprocess.run(
            cmd,
            capture_output=True,
            check=True,
        )
    except FileNotFoundError as e:
        raise FileNotFoundError("pg_restore/psql not found. Install postgresql-client.") from e
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        logger.error(f"Restore failed: {error_msg}")
        raise RuntimeError(f"Restore failed: {error_msg}") from e

    logger.info(f"Backup restored successfully: {backup_file}")


def list_backups(backup_dir: Path | None = None) -> list[dict]:
    """List available backup files.

    Args:
        backup_dir: Directory containing backups. Defaults to DEFAULT_BACKUP_DIR.

    Returns:
        List of dicts with backup info: name, path, size, created_at.
    """
    backup_dir = ensure_backup_dir(backup_dir)

    backups = []
    for f in sorted(backup_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.is_file() and (
            f.suffix == ".sql" or f.suffix == ".gz" or f.suffixes == [".sql", ".gz"]
        ):
            stat = f.stat()
            backups.append(
                {
                    "name": f.name,
                    "path": str(f),
                    "size": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )

    return backups


def get_backup_info(backup_file: Path) -> dict:
    """Get detailed information about a backup file.

    Args:
        backup_file: Path to backup file.

    Returns:
        Dict with backup info: name, path, size, created_at.

    Raises:
        FileNotFoundError: If backup file not found.
    """
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_file}")

    stat = backup_file.stat()
    return {
        "name": backup_file.name,
        "path": str(backup_file),
        "size": stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }
