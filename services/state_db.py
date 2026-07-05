import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional

from loguru import logger

from config import Settings


class StateDatabaseService:
    """轻量级 SQLite 状态库，承载业务状态而非全量扫描数据。"""

    def __init__(self):
        self.settings = Settings()
        self.db_path = self.settings.sqlite_db_path
        self._lock = threading.RLock()
        self._initialized = False

    def refresh_settings(self):
        self.settings = Settings()
        self.db_path = self.settings.sqlite_db_path

    @contextmanager
    def connection(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self):
        with self._lock:
            if self._initialized:
                return
            with self.connection() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS series_states (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        normalized_title TEXT NOT NULL,
                        title TEXT NOT NULL,
                        year TEXT,
                        media_type TEXT NOT NULL,
                        state TEXT NOT NULL,
                        library_role TEXT,
                        current_local_path TEXT,
                        current_remote_path TEXT,
                        current_strm_path TEXT,
                        last_tmdb_status TEXT,
                        last_air_date TEXT,
                        last_checked_at REAL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        UNIQUE(normalized_title, year, media_type)
                    );

                    CREATE TABLE IF NOT EXISTS state_transitions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        series_state_id INTEGER NOT NULL,
                        from_state TEXT,
                        to_state TEXT NOT NULL,
                        reason TEXT,
                        trigger_source TEXT,
                        payload_json TEXT,
                        success INTEGER NOT NULL DEFAULT 1,
                        error_message TEXT,
                        created_at REAL NOT NULL,
                        FOREIGN KEY(series_state_id) REFERENCES series_states(id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS pending_deletions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        series_state_id INTEGER,
                        path TEXT NOT NULL UNIQUE,
                        cloud_path TEXT,
                        archive_path TEXT,
                        delete_time REAL NOT NULL,
                        move_success INTEGER NOT NULL DEFAULT 1,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        FOREIGN KEY(series_state_id) REFERENCES series_states(id) ON DELETE SET NULL
                    );

                    CREATE TABLE IF NOT EXISTS missing_source_tasks (
                        id TEXT PRIMARY KEY,
                        series_state_id INTEGER,
                        video_path TEXT NOT NULL UNIQUE,
                        trigger_path TEXT,
                        reason TEXT,
                        title TEXT,
                        year TEXT,
                        season INTEGER,
                        episode INTEGER,
                        media_type TEXT,
                        filename TEXT,
                        release_profile_json TEXT,
                        neighbor_profiles_json TEXT,
                        reference_profile_json TEXT,
                        tmdb_id INTEGER,
                        status TEXT NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        message TEXT,
                        match_mode TEXT,
                        selected_resource TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        FOREIGN KEY(series_state_id) REFERENCES series_states(id) ON DELETE SET NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_series_state_title
                        ON series_states(normalized_title, year, media_type);
                    CREATE INDEX IF NOT EXISTS idx_pending_deletions_status
                        ON pending_deletions(status, delete_time);
                    CREATE INDEX IF NOT EXISTS idx_missing_source_status
                        ON missing_source_tasks(status, updated_at);
                    """
                )
            self._initialized = True
            logger.info(f"SQLite 状态库已初始化: {self.db_path}")

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return dict(row)

    @staticmethod
    def _loads_json(value: Optional[str], fallback: Any):
        if not value:
            return fallback
        try:
            return json.loads(value)
        except Exception:
            return fallback

    def upsert_series_state(
        self,
        *,
        normalized_title: str,
        title: str,
        year: Optional[str],
        media_type: str,
        state: str,
        library_role: Optional[str] = None,
        current_local_path: Optional[str] = None,
        current_remote_path: Optional[str] = None,
        current_strm_path: Optional[str] = None,
        last_tmdb_status: Optional[str] = None,
        last_air_date: Optional[str] = None,
        last_checked_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        self.initialize()
        now = time.time()
        transition_args = None
        with self._lock, self.connection() as conn:
            existing = conn.execute(
                """
                SELECT * FROM series_states
                WHERE normalized_title = ? AND ifnull(year, '') = ifnull(?, '') AND media_type = ?
                """,
                (normalized_title, year, media_type),
            ).fetchone()
            previous_state = existing["state"] if existing else None

            conn.execute(
                """
                INSERT INTO series_states (
                    normalized_title, title, year, media_type, state, library_role,
                    current_local_path, current_remote_path, current_strm_path,
                    last_tmdb_status, last_air_date, last_checked_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(normalized_title, year, media_type) DO UPDATE SET
                    title = excluded.title,
                    state = excluded.state,
                    library_role = COALESCE(excluded.library_role, series_states.library_role),
                    current_local_path = COALESCE(excluded.current_local_path, series_states.current_local_path),
                    current_remote_path = COALESCE(excluded.current_remote_path, series_states.current_remote_path),
                    current_strm_path = COALESCE(excluded.current_strm_path, series_states.current_strm_path),
                    last_tmdb_status = COALESCE(excluded.last_tmdb_status, series_states.last_tmdb_status),
                    last_air_date = COALESCE(excluded.last_air_date, series_states.last_air_date),
                    last_checked_at = COALESCE(excluded.last_checked_at, series_states.last_checked_at),
                    updated_at = excluded.updated_at
                """,
                (
                    normalized_title,
                    title,
                    year,
                    media_type,
                    state,
                    library_role,
                    current_local_path,
                    current_remote_path,
                    current_strm_path,
                    last_tmdb_status,
                    last_air_date,
                    last_checked_at,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT * FROM series_states
                WHERE normalized_title = ? AND ifnull(year, '') = ifnull(?, '') AND media_type = ?
                """,
                (normalized_title, year, media_type),
            ).fetchone()
            result = self._row_to_dict(row)
            if previous_state != state:
                transition_args = {
                    "series_state_id": result["id"],
                    "from_state": previous_state,
                    "to_state": state,
                    "reason": "state_sync",
                    "trigger_source": "system",
                    "payload": None,
                    "success": True,
                }
        if transition_args:
            self.add_transition(**transition_args)
            return result

    def add_transition(
        self,
        *,
        series_state_id: int,
        from_state: Optional[str],
        to_state: str,
        reason: Optional[str],
        trigger_source: Optional[str],
        payload: Optional[Dict[str, Any]],
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        self.initialize()
        with self._lock, self.connection() as conn:
            conn.execute(
                """
                INSERT INTO state_transitions (
                    series_state_id, from_state, to_state, reason, trigger_source,
                    payload_json, success, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    series_state_id,
                    from_state,
                    to_state,
                    reason,
                    trigger_source,
                    json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                    1 if success else 0,
                    error_message,
                    time.time(),
                ),
            )

    def find_series_state_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        self.initialize()
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM series_states
                WHERE current_local_path = ? OR current_remote_path = ? OR current_strm_path = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (path, path, path),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def find_series_state_by_identity(
        self,
        *,
        normalized_title: str,
        year: Optional[str],
        media_type: str,
    ) -> Optional[Dict[str, Any]]:
        self.initialize()
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM series_states
                WHERE normalized_title = ? AND ifnull(year, '') = ifnull(?, '') AND media_type = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (normalized_title, year, media_type),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_pending_deletions(self) -> List[Dict[str, Any]]:
        self.initialize()
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM pending_deletions
                WHERE status != 'removed'
                ORDER BY delete_time ASC
                """
            ).fetchall()
        results = []
        for row in rows:
            item = self._row_to_dict(row)
            item["move_success"] = bool(item.get("move_success", 1))
            results.append(item)
        return results

    def replace_pending_deletions(self, items: Iterable[Dict[str, Any]]) -> None:
        self.initialize()
        normalized = list(items)
        with self._lock, self.connection() as conn:
            conn.execute("DELETE FROM pending_deletions")
            for item in normalized:
                conn.execute(
                    """
                    INSERT INTO pending_deletions (
                        series_state_id, path, cloud_path, archive_path,
                        delete_time, move_success, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.get("series_state_id"),
                        item["path"],
                        item.get("cloud_path"),
                        item.get("archive_path"),
                        item["delete_time"],
                        1 if item.get("move_success", True) else 0,
                        item.get("status", "pending"),
                        item.get("created_at", time.time()),
                        item.get("updated_at", time.time()),
                    ),
                )

    def upsert_pending_deletion(self, item: Dict[str, Any]) -> None:
        self.initialize()
        now = time.time()
        with self._lock, self.connection() as conn:
            conn.execute(
                """
                INSERT INTO pending_deletions (
                    series_state_id, path, cloud_path, archive_path,
                    delete_time, move_success, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    series_state_id = COALESCE(excluded.series_state_id, pending_deletions.series_state_id),
                    cloud_path = excluded.cloud_path,
                    archive_path = excluded.archive_path,
                    delete_time = excluded.delete_time,
                    move_success = excluded.move_success,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    item.get("series_state_id"),
                    item["path"],
                    item.get("cloud_path"),
                    item.get("archive_path"),
                    item["delete_time"],
                    1 if item.get("move_success", True) else 0,
                    item.get("status", "pending"),
                    item.get("created_at", now),
                    item.get("updated_at", now),
                ),
            )

    def remove_pending_deletion(self, path: str) -> None:
        self.initialize()
        with self._lock, self.connection() as conn:
            conn.execute("DELETE FROM pending_deletions WHERE path = ?", (path,))

    def get_missing_source_tasks(self) -> List[Dict[str, Any]]:
        self.initialize()
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM missing_source_tasks
                ORDER BY updated_at DESC
                """
            ).fetchall()
        results = []
        for row in rows:
            item = self._row_to_dict(row)
            item["release_profile"] = self._loads_json(item.pop("release_profile_json", None), {})
            item["neighbor_profiles"] = self._loads_json(item.pop("neighbor_profiles_json", None), [])
            item["reference_profile"] = self._loads_json(item.pop("reference_profile_json", None), {})
            results.append(item)
        return results

    def replace_missing_source_tasks(self, items: Iterable[Dict[str, Any]]) -> None:
        self.initialize()
        normalized = list(items)
        with self._lock, self.connection() as conn:
            conn.execute("DELETE FROM missing_source_tasks")
            for item in normalized:
                self._upsert_missing_source_task_conn(conn, item)

    def upsert_missing_source_task(self, item: Dict[str, Any]) -> None:
        self.initialize()
        with self._lock, self.connection() as conn:
            self._upsert_missing_source_task_conn(conn, item)

    def _upsert_missing_source_task_conn(self, conn: sqlite3.Connection, item: Dict[str, Any]) -> None:
        now = time.time()
        conn.execute(
            """
            INSERT INTO missing_source_tasks (
                id, series_state_id, video_path, trigger_path, reason, title, year,
                season, episode, media_type, filename, release_profile_json,
                neighbor_profiles_json, reference_profile_json, tmdb_id, status,
                attempts, message, match_mode, selected_resource, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                series_state_id = COALESCE(excluded.series_state_id, missing_source_tasks.series_state_id),
                video_path = excluded.video_path,
                trigger_path = excluded.trigger_path,
                reason = excluded.reason,
                title = excluded.title,
                year = excluded.year,
                season = excluded.season,
                episode = excluded.episode,
                media_type = excluded.media_type,
                filename = excluded.filename,
                release_profile_json = excluded.release_profile_json,
                neighbor_profiles_json = excluded.neighbor_profiles_json,
                reference_profile_json = excluded.reference_profile_json,
                tmdb_id = excluded.tmdb_id,
                status = excluded.status,
                attempts = excluded.attempts,
                message = excluded.message,
                match_mode = excluded.match_mode,
                selected_resource = excluded.selected_resource,
                updated_at = excluded.updated_at
            """,
            (
                item["id"],
                item.get("series_state_id"),
                item["video_path"],
                item.get("trigger_path"),
                item.get("reason"),
                item.get("title"),
                item.get("year"),
                item.get("season"),
                item.get("episode"),
                item.get("media_type"),
                item.get("filename"),
                json.dumps(item.get("release_profile") or {}, ensure_ascii=False),
                json.dumps(item.get("neighbor_profiles") or [], ensure_ascii=False),
                json.dumps(item.get("reference_profile") or {}, ensure_ascii=False),
                item.get("tmdb_id"),
                item.get("status", "pending"),
                item.get("attempts", 0),
                item.get("message"),
                item.get("match_mode"),
                item.get("selected_resource"),
                item.get("created_at", now),
                item.get("updated_at", now),
            ),
        )

    def get_active_missing_source_tasks_by_series(self, series_state_id: int) -> List[Dict[str, Any]]:
        self.initialize()
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM missing_source_tasks
                WHERE series_state_id = ? AND status IN ('pending', 'subscribed', 'downloading')
                ORDER BY updated_at DESC
                """,
                (series_state_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]
