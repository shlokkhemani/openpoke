"""
Admin routes for Railway Volume data management.

Provides endpoints for:
- Health monitoring
- Backup management
- Data export/import
"""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.data_manager import get_data_manager

router = APIRouter(prefix="/data-admin", tags=["data-admin"])


class BackupRequest(BaseModel):
    """Request to restore from backup."""
    filename: str


class ExportResponse(BaseModel):
    """Response containing exported data."""
    success: bool
    data: Dict[str, Any]


@router.get("/health")
def get_health_status() -> Dict[str, Any]:
    """
    Get health status of Railway Volume storage system.

    Returns:
        Dictionary with storage metrics, backup counts, and system status
    """
    data_manager = get_data_manager()
    return data_manager.get_health_status()


@router.get("/export")
def export_all_data() -> ExportResponse:
    """
    Export all data from Railway Volume.

    Useful for:
    - Manual backups
    - Data migration
    - Debugging

    Returns:
        All JSON files in a single export package
    """
    try:
        data_manager = get_data_manager()
        export = data_manager.export_all_data()

        return ExportResponse(
            success=True,
            data=export
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/restore-backup")
def restore_from_backup(request: BackupRequest) -> Dict[str, Any]:
    """
    Restore a file from its most recent backup.

    Args:
        request: Backup request with filename

    Returns:
        Status of restore operation
    """
    try:
        data_manager = get_data_manager()
        success = data_manager.restore_from_backup(request.filename)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"No backup found for {request.filename}"
            )

        return {
            "success": True,
            "message": f"Restored {request.filename} from backup"
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/storage-info")
def get_storage_info() -> Dict[str, Any]:
    """
    Get detailed storage information.

    Returns:
        Information about files, sizes, and Railway Volume usage
    """
    try:
        from pathlib import Path
        from ..services.data_manager import DATA_DIR, BACKUPS_DIR

        data_files = []
        for json_file in DATA_DIR.glob("*.json"):
            stat = json_file.stat()
            data_files.append({
                "name": json_file.name,
                "size_bytes": stat.st_size,
                "size_kb": round(stat.st_size / 1024, 2),
                "modified": stat.st_mtime
            })

        backups = []
        for backup_file in BACKUPS_DIR.glob("*.json"):
            stat = backup_file.stat()
            backups.append({
                "name": backup_file.name,
                "size_bytes": stat.st_size,
                "size_kb": round(stat.st_size / 1024, 2),
                "created": stat.st_mtime
            })

        total_data_size = sum(f["size_bytes"] for f in data_files)
        total_backup_size = sum(b["size_bytes"] for b in backups)

        return {
            "mount_path": str(DATA_DIR),
            "data_files": data_files,
            "backups": backups,
            "summary": {
                "total_data_files": len(data_files),
                "total_backups": len(backups),
                "total_data_size_mb": round(total_data_size / (1024 * 1024), 2),
                "total_backup_size_mb": round(total_backup_size / (1024 * 1024), 2),
                "total_size_mb": round((total_data_size + total_backup_size) / (1024 * 1024), 2),
                "volume_limit_mb": 500,
                "usage_percent": round(
                    ((total_data_size + total_backup_size) / (500 * 1024 * 1024)) * 100,
                    2
                )
            }
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
