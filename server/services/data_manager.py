"""
Centralized data manager for Railway Volume persistence.

Manages all data storage with automatic backups, validation, and atomic writes.
Optimized for single-user usage with Railway Volumes mounted at /app/server/data
"""

import json
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging_config import logger

# Railway Volume mount point
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BACKUPS_DIR = DATA_DIR / "backups"
CONVERSATION_HISTORY_DIR = DATA_DIR / "conversation_history"

# Configuration
MAX_BACKUPS = 5  # Keep last 5 backups per file
BACKUP_ON_WRITE = True  # Auto-backup before critical writes


class DataManager:
    """
    Thread-safe data manager with automatic backups and validation.

    Features:
    - Atomic writes (write to temp file, then rename)
    - Automatic backups with rotation
    - Data validation
    - Thread-safe operations
    - Health checks
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._ensure_directories()
        self._initialize_metadata()

    def _ensure_directories(self) -> None:
        """Create necessary directories in the Railway Volume."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
            CONVERSATION_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            logger.info("✅ Data directories initialized", extra={"path": str(DATA_DIR)})
        except Exception as exc:
            logger.error("❌ Failed to create data directories", extra={"error": str(exc)})
            raise

    def _initialize_metadata(self) -> None:
        """Initialize metadata file with system info."""
        metadata_path = DATA_DIR / "metadata.json"
        if not metadata_path.exists():
            metadata = {
                "schema_version": "1.0.0",
                "created_at": datetime.now().isoformat(),
                "last_backup": None,
                "total_writes": 0,
                "storage_info": {
                    "mount_path": "/app/server/data",
                    "max_size_mb": 500,
                    "region": "EU West (Amsterdam)"
                }
            }
            self._write_json_atomic(metadata_path, metadata)
            logger.info("✅ Metadata initialized")

    def _write_json_atomic(self, path: Path, data: Dict[str, Any]) -> None:
        """
        Write JSON atomically to prevent corruption.

        Steps:
        1. Write to temporary file
        2. Sync to disk
        3. Rename to target (atomic operation on POSIX)
        """
        temp_path = path.with_suffix(".tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()  # Flush to OS buffer
                # Note: os.fsync(f.fileno()) would be ideal but can cause issues in containers

            # Atomic rename
            temp_path.replace(path)

        except Exception as exc:
            if temp_path.exists():
                temp_path.unlink()
            raise exc

    def _read_json(self, path: Path) -> Dict[str, Any]:
        """Read and validate JSON file."""
        try:
            if not path.exists():
                return {}

            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                logger.warning(f"⚠️ Invalid JSON structure in {path.name}, returning empty dict")
                return {}

            return data

        except json.JSONDecodeError as exc:
            logger.error(
                f"❌ JSON decode error in {path.name}",
                extra={"error": str(exc), "path": str(path)}
            )
            # Try to restore from backup
            backup = self._get_latest_backup(path.name)
            if backup:
                logger.info(f"🔄 Restoring {path.name} from backup {backup.name}")
                shutil.copy(backup, path)
                return self._read_json(path)  # Retry after restore
            return {}

        except Exception as exc:
            logger.error(f"❌ Error reading {path.name}", extra={"error": str(exc)})
            return {}

    def _create_backup(self, file_path: Path) -> Optional[Path]:
        """
        Create timestamped backup of a file.

        Returns:
            Path to backup file, or None if backup failed
        """
        if not file_path.exists():
            return None

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
            backup_path = BACKUPS_DIR / backup_name

            shutil.copy2(file_path, backup_path)

            # Rotate old backups
            self._rotate_backups(file_path.name)

            logger.info(f"💾 Backup created: {backup_name}")
            return backup_path

        except Exception as exc:
            logger.error(f"❌ Backup failed for {file_path.name}", extra={"error": str(exc)})
            return None

    def _rotate_backups(self, filename: str) -> None:
        """Keep only the last N backups for a file."""
        try:
            pattern = f"{Path(filename).stem}_*{Path(filename).suffix}"
            backups = sorted(BACKUPS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime)

            # Delete oldest backups if we exceed MAX_BACKUPS
            while len(backups) > MAX_BACKUPS:
                oldest = backups.pop(0)
                oldest.unlink()
                logger.info(f"🗑️ Rotated old backup: {oldest.name}")

        except Exception as exc:
            logger.warning(f"⚠️ Backup rotation failed", extra={"error": str(exc)})

    def _get_latest_backup(self, filename: str) -> Optional[Path]:
        """Get the most recent backup for a file."""
        try:
            pattern = f"{Path(filename).stem}_*{Path(filename).suffix}"
            backups = sorted(BACKUPS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
            return backups[0] if backups else None
        except Exception:
            return None

    def _update_metadata(self, operation: str) -> None:
        """Update metadata after operations."""
        try:
            metadata_path = DATA_DIR / "metadata.json"
            metadata = self._read_json(metadata_path)

            metadata["total_writes"] = metadata.get("total_writes", 0) + 1
            metadata["last_operation"] = operation
            metadata["last_updated"] = datetime.now().isoformat()

            self._write_json_atomic(metadata_path, metadata)
        except Exception as exc:
            logger.warning(f"⚠️ Metadata update failed", extra={"error": str(exc)})

    # Public API

    def save_json(self, filename: str, data: Dict[str, Any], backup: bool = BACKUP_ON_WRITE) -> bool:
        """
        Save JSON data with optional backup.

        Args:
            filename: Name of the JSON file (e.g., "user_profile.json")
            data: Dictionary to save
            backup: Whether to create backup before writing

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                file_path = DATA_DIR / filename

                logger.info(
                    f"💾 Starting save for {filename}",
                    extra={
                        "file_path": str(file_path),
                        "data_keys": list(data.keys()) if isinstance(data, dict) else "not_a_dict",
                        "backup": backup
                    }
                )

                # Create backup if requested and file exists
                if backup and file_path.exists():
                    backup_path = self._create_backup(file_path)
                    logger.info(f"📦 Backup created: {backup_path.name if backup_path else 'failed'}")

                # Atomic write
                self._write_json_atomic(file_path, data)

                # Verify the file was written
                if not file_path.exists():
                    logger.error(f"❌ File does not exist after write: {file_path}")
                    return False

                size = file_path.stat().st_size
                logger.info(f"✅ File written: {filename} ({size} bytes)")

                # Verify we can read it back
                with file_path.open("r") as f:
                    loaded = json.load(f)
                    logger.info(f"✅ Verified read-back: {list(loaded.keys()) if isinstance(loaded, dict) else 'not_a_dict'}")

                # Update metadata
                self._update_metadata(f"save:{filename}")

                logger.info(f"✅ Saved {filename}", extra={"size_bytes": size})
                return True

            except Exception as exc:
                logger.error(
                    f"❌ Failed to save {filename}",
                    extra={"error": str(exc), "error_type": type(exc).__name__}
                )
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                return False

    def load_json(self, filename: str) -> Dict[str, Any]:
        """
        Load JSON data.

        Args:
            filename: Name of the JSON file

        Returns:
            Dictionary with data, or empty dict if file doesn't exist
        """
        with self._lock:
            file_path = DATA_DIR / filename

            logger.info(
                f"📖 Loading {filename}",
                extra={
                    "file_path": str(file_path),
                    "exists": file_path.exists(),
                    "size": file_path.stat().st_size if file_path.exists() else 0
                }
            )

            data = self._read_json(file_path)

            logger.info(
                f"✅ Loaded {filename}",
                extra={
                    "data_keys": list(data.keys()) if isinstance(data, dict) else "not_a_dict",
                    "empty": len(data) == 0
                }
            )

            return data

    def update_field(self, filename: str, key: str, value: Any, backup: bool = True) -> bool:
        """
        Update a single field in a JSON file.

        Args:
            filename: Name of the JSON file
            key: Key to update
            value: New value
            backup: Whether to backup before update

        Returns:
            True if successful
        """
        data = self.load_json(filename)
        data[key] = value
        return self.save_json(filename, data, backup=backup)

    def delete_file(self, filename: str, backup: bool = True) -> bool:
        """
        Delete a file (with optional backup).

        Args:
            filename: Name of file to delete
            backup: Whether to backup before deletion

        Returns:
            True if successful
        """
        with self._lock:
            try:
                file_path = DATA_DIR / filename

                if not file_path.exists():
                    return True

                if backup:
                    self._create_backup(file_path)

                file_path.unlink()
                logger.info(f"🗑️ Deleted {filename}")
                return True

            except Exception as exc:
                logger.error(f"❌ Failed to delete {filename}", extra={"error": str(exc)})
                return False

    def restore_from_backup(self, filename: str) -> bool:
        """
        Restore a file from its most recent backup.

        Args:
            filename: Name of file to restore

        Returns:
            True if successful
        """
        with self._lock:
            try:
                backup = self._get_latest_backup(filename)
                if not backup:
                    logger.error(f"❌ No backup found for {filename}")
                    return False

                target_path = DATA_DIR / filename
                shutil.copy2(backup, target_path)

                logger.info(f"🔄 Restored {filename} from {backup.name}")
                return True

            except Exception as exc:
                logger.error(f"❌ Restore failed for {filename}", extra={"error": str(exc)})
                return False

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get health status of the data storage system.

        Returns:
            Dictionary with health metrics
        """
        try:
            metadata = self.load_json("metadata.json")

            # Calculate storage usage
            total_size = sum(f.stat().st_size for f in DATA_DIR.rglob("*") if f.is_file())
            backup_size = sum(f.stat().st_size for f in BACKUPS_DIR.rglob("*") if f.is_file())

            # Count backups
            backup_count = len(list(BACKUPS_DIR.glob("*.json")))

            return {
                "status": "healthy",
                "mount_path": str(DATA_DIR),
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "backup_size_mb": round(backup_size / (1024 * 1024), 2),
                "backup_count": backup_count,
                "metadata": metadata,
                "directories": {
                    "data": DATA_DIR.exists(),
                    "backups": BACKUPS_DIR.exists(),
                    "conversation_history": CONVERSATION_HISTORY_DIR.exists()
                }
            }

        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc)
            }

    def export_all_data(self) -> Dict[str, Any]:
        """
        Export all data for backup/migration.

        Returns:
            Dictionary with all JSON files
        """
        export = {
            "exported_at": datetime.now().isoformat(),
            "files": {}
        }

        for json_file in DATA_DIR.glob("*.json"):
            if json_file.name != "metadata.json":
                export["files"][json_file.name] = self.load_json(json_file.name)

        return export


# Singleton instance
_data_manager: Optional[DataManager] = None
_manager_lock = threading.Lock()


def get_data_manager() -> DataManager:
    """Get the singleton DataManager instance."""
    global _data_manager

    if _data_manager is None:
        with _manager_lock:
            if _data_manager is None:
                _data_manager = DataManager()

    return _data_manager


__all__ = ["DataManager", "get_data_manager", "DATA_DIR", "BACKUPS_DIR"]
