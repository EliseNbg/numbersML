"""
Backup and restore API endpoints.

Provides REST API for database backup and restore operations:
- Create a new backup
- List available backups
- Restore from a backup
- Get backup details
"""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.application.services.backup_service import BackupService
from src.infrastructure.database.backup import DEFAULT_BACKUP_DIR
from src.infrastructure.database.config import get_db_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backup", tags=["backup"])


class BackupInfo(BaseModel):
    """Backup file information."""

    name: str
    path: str
    size: int
    created_at: str


class BackupCreateResponse(BaseModel):
    """Response for backup creation."""

    name: str
    path: str
    size: int
    created_at: str


class RestoreResponse(BaseModel):
    """Response for restore operation."""

    status: str
    message: str


async def get_backup_service() -> BackupService:
    """Get BackupService instance with database URL."""
    db_url = get_db_url()
    return BackupService(db_url=db_url)


@router.post(
    "/create",
    response_model=BackupCreateResponse,
    summary="Create database backup",
    description="Create a new backup of the current database state",
)
async def create_backup(
    compress: bool = True,
    service: BackupService = Depends(get_backup_service),  # noqa: B008
) -> BackupCreateResponse:
    """
    Create a database backup.

    Args:
        compress: Whether to compress the backup (default: True).

    Returns:
        BackupInfo with name, path, size, created_at.

    Raises:
        HTTPException: If backup fails.
    """
    try:
        result = await service.create_backup(compress=compress)
        return BackupCreateResponse(**result)
    except RuntimeError as e:
        logger.error(f"Backup failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.get(
    "/list",
    response_model=list[BackupInfo],
    summary="List available backups",
    description="List all available database backups",
)
async def list_backups(
    service: BackupService = Depends(get_backup_service),  # noqa: B008
) -> list[BackupInfo]:
    """
    List available backups.

    Returns:
        List of BackupInfo objects.
    """
    backups = await service.list_backups()
    return [BackupInfo(**b) for b in backups]


@router.get(
    "/details/{backup_name}",
    response_model=BackupInfo,
    summary="Get backup details",
    description="Get detailed information about a specific backup",
)
async def get_backup_details(
    backup_name: str,
    service: BackupService = Depends(get_backup_service),  # noqa: B008
) -> BackupInfo:
    """
    Get details of a specific backup.

    Args:
        backup_name: Name of the backup file.

    Returns:
        BackupInfo with backup details.

    Raises:
        HTTPException: If backup not found.
    """
    try:
        result = await service.get_backup_details(backup_name)
        return BackupInfo(**result)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup not found: {backup_name}",
        ) from e


@router.post(
    "/restore/{backup_name}",
    response_model=RestoreResponse,
    summary="Restore database from backup",
    description="Restore the database from a specified backup file",
)
async def restore_backup(
    backup_name: str,
    service: BackupService = Depends(get_backup_service),  # noqa: B008
) -> RestoreResponse:
    """
    Restore database from backup.

    Args:
        backup_name: Name of the backup file to restore.

    Returns:
        RestoreResponse with status message.

    Raises:
        HTTPException: If restore fails or backup not found.
    """
    try:
        result = await service.restore_backup(backup_name)
        return RestoreResponse(**result)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup not found: {backup_name}",
        ) from e
    except RuntimeError as e:
        logger.error(f"Restore failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.get(
    "/download/{backup_name}",
    summary="Download backup file",
    description="Download a specific backup file",
)
async def download_backup(backup_name: str):
    """
    Download a backup file.

    Args:
        backup_name: Name of the backup file.

    Returns:
        FileResponse with the backup file.

    Raises:
        HTTPException: If backup not found.
    """
    backup_path = DEFAULT_BACKUP_DIR / backup_name

    if not backup_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup not found: {backup_name}",
        )

    return FileResponse(
        path=str(backup_path),
        filename=backup_name,
        media_type="application/octet-stream",
    )


@router.post(
    "/upload",
    response_model=BackupInfo,
    summary="Upload backup file",
    description="Upload a backup file to restore later",
)
async def upload_backup(
    file: UploadFile = File(...),  # noqa: B008
    service: BackupService = Depends(get_backup_service),  # noqa: B008
) -> BackupInfo:
    """
    Upload a backup file.

    Args:
        file: Backup file to upload.

    Returns:
        BackupInfo with uploaded file info.

    Raises:
        HTTPException: If upload fails.
    """
    try:
        backup_dir = DEFAULT_BACKUP_DIR
        backup_dir.mkdir(parents=True, exist_ok=True)

        file_path = backup_dir / file.filename
        content = await file.read()

        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"Backup uploaded: {file_path}")

        from src.infrastructure.database.backup import get_backup_info

        info = get_backup_info(file_path)
        return BackupInfo(**info)

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {e}",
        ) from e


@router.delete(
    "/delete/{backup_name}",
    summary="Delete backup file",
    description="Delete a specific backup file",
)
async def delete_backup(backup_name: str):
    """
    Delete a backup file.

    Args:
        backup_name: Name of the backup file to delete.

    Returns:
        Success message.

    Raises:
        HTTPException: If backup not found or delete fails.
    """
    backup_path = DEFAULT_BACKUP_DIR / backup_name

    if not backup_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup not found: {backup_name}",
        )

    try:
        backup_path.unlink()
        logger.info(f"Backup deleted: {backup_name}")
        return {"status": "success", "message": f"Backup deleted: {backup_name}"}
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Delete failed: {e}",
        ) from e
