import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

import httpx

from config import Settings

logger = logging.getLogger(__name__)

YEAR_PATTERN = re.compile(r"\((\d{4})\)")
SEASON_PATTERN = re.compile(r"(?:season\s*(\d+)|s(\d+)|第\s*(\d+)\s*季)", re.IGNORECASE)


class MoviePilotService:
    def __init__(self):
        self.settings = Settings()
        self._token: Optional[str] = None
        self.queue_file = Path("data/moviepilot_missing_sources.json")
        self._queue: List[Dict[str, Any]] = []
        self.refresh_settings()
        self._load_queue()

    def refresh_settings(self):
        self.settings = Settings()
        self.enabled = self.settings.moviepilot_enabled
        self.base_url = (self.settings.moviepilot_url or "").rstrip("/")
        self.username = self.settings.moviepilot_username
        self.password = self.settings.moviepilot_password
        self.api_key = self.settings.moviepilot_api_key
        self.auto_submit = self.settings.moviepilot_auto_submit
        if not self.base_url:
            self.enabled = False

    def _load_queue(self):
        if self.queue_file.exists():
            try:
                self._queue = json.loads(self.queue_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"加载 MoviePilot 缺源队列失败: {e}")
                self._queue = []

    def _save_queue(self):
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        self.queue_file.write_text(json.dumps(self._queue, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_queue(self) -> List[Dict[str, Any]]:
        return sorted(self._queue, key=lambda item: item.get("updated_at", 0), reverse=True)

    async def get_status(self) -> Dict[str, Any]:
        status = {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "queue_count": len(self._queue),
            "auth_mode": "disabled",
            "server_ok": False,
            "auth_ok": False,
        }
        if not self.enabled:
            return status

        status["auth_mode"] = "api_key" if self.api_key else "password"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/v1/system/status")
                status["server_ok"] = response.status_code == 200
        except Exception:
            status["server_ok"] = False
        try:
            status["auth_ok"] = await self.test_connection()
        except Exception:
            status["auth_ok"] = False
        return status

    async def test_connection(self) -> bool:
        if not self.enabled:
            return False

        response = await self._request("GET", "/api/v1/subscribe/")
        return isinstance(response, list)

    async def _get_headers(self) -> Dict[str, str]:
        if self.api_key:
            return {"X-API-KEY": self.api_key, "User-Agent": "alist-strm/1.0"}

        if not self.username or not self.password:
            raise RuntimeError("MoviePilot 用户名或密码未配置")

        if not self._token:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/login/access-token",
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "accept": "application/json",
                    },
                    data={"username": self.username, "password": self.password},
                )
                response.raise_for_status()
                token_data = response.json()
                self._token = token_data.get("access_token")
                if not self._token:
                    raise RuntimeError("未获取到 MoviePilot access_token")

        return {"Authorization": f"Bearer {self._token}", "User-Agent": "alist-strm/1.0"}

    async def _request(self, method: str, path: str, retry_on_unauthorized: bool = True, **kwargs):
        headers = kwargs.pop("headers", None) or await self._get_headers()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
            if response.status_code == 401 and retry_on_unauthorized and not self.api_key:
                self._token = None
                refreshed_headers = await self._get_headers()
                response = await client.request(method, f"{self.base_url}{path}", headers=refreshed_headers, **kwargs)
            response.raise_for_status()
            if not response.text:
                return None
            return response.json()

    @staticmethod
    def infer_media_from_path(video_path: str) -> Dict[str, Any]:
        decoded = unquote(video_path).rstrip("/")
        parts = [part for part in decoded.split("/") if part]
        title = parts[-2] if len(parts) >= 2 else parts[-1] if parts else decoded
        season = None

        for idx in range(len(parts) - 1, -1, -1):
            match = SEASON_PATTERN.search(parts[idx])
            if match:
                season = int(next(group for group in match.groups() if group))
                if idx > 0:
                    title = parts[idx - 1]
                break

        year_match = YEAR_PATTERN.search(title)
        year = year_match.group(1) if year_match else None
        normalized_title = YEAR_PATTERN.sub("", title).strip().strip("-_")

        return {
            "title": normalized_title or title,
            "year": year,
            "season": season,
            "media_type": "tv" if season else "movie",
        }

    def enqueue_missing_source(self, video_path: str, source_reason: str, trigger_path: Optional[str] = None) -> Dict[str, Any]:
        media = self.infer_media_from_path(video_path)
        normalized_path = unquote(video_path)

        for item in self._queue:
            if item.get("video_path") == normalized_path and item.get("status") in {"pending", "subscribed"}:
                return item

        entry = {
            "id": f"mp_{int(time.time() * 1000)}_{len(self._queue)}",
            "video_path": normalized_path,
            "trigger_path": trigger_path,
            "reason": source_reason,
            "title": media["title"],
            "year": media["year"],
            "season": media["season"],
            "media_type": media["media_type"],
            "tmdb_id": None,
            "status": "pending",
            "attempts": 0,
            "created_at": time.time(),
            "updated_at": time.time(),
            "message": None,
        }
        self._queue.append(entry)
        self._save_queue()
        return entry

    async def search_media(self, title: str) -> List[Dict[str, Any]]:
        return await self._request("GET", "/api/v1/media/search", params={"title": title, "type": "media", "page": 1, "count": 8})

    @staticmethod
    def _pick_best_match(candidates: List[Dict[str, Any]], title: str, year: Optional[str], media_type: str) -> Optional[Dict[str, Any]]:
        if not candidates:
            return None
        normalized_title = title.strip().lower()
        filtered = []
        for item in candidates:
            item_title = str(item.get("title") or item.get("name") or "").strip().lower()
            item_year = str(item.get("year") or item.get("release_date") or "")
            item_type = str(item.get("type") or item.get("media_type") or "").lower()
            score = 0
            if item_title == normalized_title:
                score += 5
            elif normalized_title and normalized_title in item_title:
                score += 3
            if year and year in item_year:
                score += 3
            if media_type == "movie" and any(k in item_type for k in ["movie", "电影"]):
                score += 2
            if media_type == "tv" and any(k in item_type for k in ["tv", "series", "show", "电视剧"]):
                score += 2
            filtered.append((score, item))
        filtered.sort(key=lambda x: x[0], reverse=True)
        return filtered[0][1] if filtered and filtered[0][0] > 0 else candidates[0]

    async def submit_queue_item(self, item_id: str) -> Dict[str, Any]:
        item = next((entry for entry in self._queue if entry["id"] == item_id), None)
        if not item:
            raise ValueError("订阅项不存在")
        if not self.enabled:
            raise RuntimeError("MoviePilot 未启用")

        item["attempts"] += 1
        item["updated_at"] = time.time()

        try:
            matches = await self.search_media(item["title"])
            match = self._pick_best_match(matches or [], item["title"], item.get("year"), item["media_type"])
            if not match:
                item["status"] = "failed"
                item["message"] = "未找到匹配的媒体信息"
                self._save_queue()
                return item

            tmdb_id = match.get("tmdb_id") or match.get("tmdbid") or match.get("id")
            payload = {
                "name": match.get("title") or item["title"],
                "tmdbid": int(tmdb_id) if tmdb_id else None,
                "year": str(match.get("year") or item.get("year") or "") or None,
            }
            if item["media_type"] == "movie":
                payload["type"] = "电影"
            else:
                payload["season"] = item.get("season")

            response = await self._request("POST", "/api/v1/subscribe/", json=payload)
            success = bool(response and response.get("success"))
            item["tmdb_id"] = payload.get("tmdbid")
            item["status"] = "subscribed" if success else "failed"
            item["message"] = response.get("message") if isinstance(response, dict) else None
            item["updated_at"] = time.time()
            self._save_queue()
            return item
        except Exception as e:
            item["status"] = "failed"
            item["message"] = str(e)
            item["updated_at"] = time.time()
            self._save_queue()
            logger.error(f"提交 MoviePilot 订阅失败: {e}")
            return item
