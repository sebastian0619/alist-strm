from typing import Any, Dict, Optional
from urllib.parse import unquote

from loguru import logger

from config import Settings


class LifecycleService:
    """媒体生命周期状态服务，集中管理完结/连载/待删等业务状态。"""

    def __init__(self):
        self.settings = Settings()

    def refresh_settings(self):
        self.settings = Settings()

    @staticmethod
    def _normalize_title(title: str) -> str:
        return " ".join((title or "").strip().lower().split())

    @staticmethod
    def _extract_series_identity(path: str) -> Dict[str, Optional[str]]:
        normalized = unquote(path or "").replace("\\", "/").rstrip("/")
        parts = [part for part in normalized.split("/") if part]
        title = parts[-1] if parts else normalized
        year = None

        if parts:
            for idx in range(len(parts) - 1, -1, -1):
                if "(" in parts[idx] and ")" in parts[idx]:
                    title = parts[idx]
                    break

        if " (" in title and title.endswith(")"):
            raw_title, year_part = title.rsplit("(", 1)
            year = year_part[:-1]
            title = raw_title.strip()

        return {
            "title": title,
            "normalized_title": LifecycleService._normalize_title(title),
            "year": year,
        }

    @staticmethod
    def infer_library_role(path: str) -> Optional[str]:
        normalized = unquote(path or "").replace("\\", "/")
        if "/连载动漫/" in normalized or "/airing/" in normalized.lower():
            return "airing"
        if "/完结动漫/" in normalized or "/archive/" in normalized.lower():
            return "ended"
        return None

    @staticmethod
    def build_revival_path(path: str) -> str:
        """将完结目录路径转换为连载目录路径。"""
        normalized = unquote(path or "").replace("\\", "/").rstrip("/")
        if "/archive/" in normalized:
            normalized = normalized.replace("/archive/", "/", 1)
        if "/完结动漫/" in normalized:
            return normalized.replace("/完结动漫/", "/连载动漫/", 1)
        return normalized

    def build_revival_paths(
        self,
        *,
        local_path: Optional[str],
        remote_path: Optional[str],
        strm_root_path: Optional[str],
    ) -> Dict[str, Optional[str]]:
        """基于当前完结路径，计算复连载后的目标路径。"""
        target_local = self.build_revival_path(local_path) if local_path else None
        target_remote = self.build_revival_path(remote_path) if remote_path else None
        target_strm = self.build_revival_path(strm_root_path) if strm_root_path else None
        return {
            "target_local_path": target_local,
            "target_remote_path": target_remote,
            "target_strm_path": target_strm,
        }

    def infer_state(
        self,
        *,
        local_path: Optional[str] = None,
        remote_path: Optional[str] = None,
        tmdb_status: Optional[str] = None,
        pending_deletion: bool = False,
        local_exists: Optional[bool] = None,
        missing_source_active: bool = False,
    ) -> str:
        role = self.infer_library_role(local_path or remote_path or "")

        if missing_source_active:
            return "recovery_needed"

        if tmdb_status == "Returning Series" and role == "ended":
            return "revived"

        if pending_deletion:
            return "archived_pending_delete"

        if local_exists is False and role == "ended":
            return "archived_remote_only"

        if role == "airing":
            return "airing_local"

        if role == "ended":
            return "archived_pending_delete" if local_exists else "archived_remote_only"

        return "unknown"

    def sync_series_state(
        self,
        state_db,
        *,
        local_path: Optional[str] = None,
        remote_path: Optional[str] = None,
        strm_path: Optional[str] = None,
        tmdb_status: Optional[str] = None,
        last_air_date: Optional[str] = None,
        pending_deletion: bool = False,
        local_exists: Optional[bool] = None,
        missing_source_active: bool = False,
        reason: str = "sync",
    ) -> Optional[Dict[str, Any]]:
        identity_path = local_path or remote_path or strm_path
        if not identity_path:
            return None

        identity = self._extract_series_identity(identity_path)
        if not identity["normalized_title"]:
            return None

        role = self.infer_library_role(local_path or remote_path or identity_path)
        state = self.infer_state(
            local_path=local_path,
            remote_path=remote_path,
            tmdb_status=tmdb_status,
            pending_deletion=pending_deletion,
            local_exists=local_exists,
            missing_source_active=missing_source_active,
        )

        row = state_db.upsert_series_state(
            normalized_title=identity["normalized_title"],
            title=identity["title"] or identity["normalized_title"],
            year=identity["year"],
            media_type="tv",
            state=state,
            library_role=role,
            current_local_path=local_path,
            current_remote_path=remote_path,
            current_strm_path=strm_path,
            last_tmdb_status=tmdb_status,
            last_air_date=last_air_date,
        )
        logger.debug(f"同步媒体生命周期状态: {identity['title']} -> {state} ({reason})")
        return row

    def record_transition(
        self,
        state_db,
        *,
        series_state_id: int,
        from_state: Optional[str],
        to_state: str,
        reason: str,
        trigger_source: str = "system",
        payload: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        state_db.add_transition(
            series_state_id=series_state_id,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            trigger_source=trigger_source,
            payload=payload,
            success=success,
            error_message=error_message,
        )
