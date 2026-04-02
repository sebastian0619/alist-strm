import json
import logging
import re
import time
import base64
import binascii
import hashlib
import hmac
import importlib
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

import httpx

from config import Settings

logger = logging.getLogger(__name__)

YEAR_PATTERN = re.compile(r"\((\d{4})\)")
SEASON_PATTERN = re.compile(r"(?:season\s*(\d+)|s(\d+)|第\s*(\d+)\s*季)", re.IGNORECASE)
EPISODE_PATTERN = re.compile(r"(?:s\d+e(\d{1,3})|ep?(\d{1,3})|第\s*(\d{1,3})\s*[集话])", re.IGNORECASE)
BRACKET_EPISODE_PATTERN = re.compile(r"[\[\(](\d{1,3})[\]\)]")
DASH_EPISODE_PATTERN = re.compile(r"(?:^|[\s._-])(\d{1,3})(?=[\s._-]|$)")
RESOLUTION_PATTERN = re.compile(r"\b(2160p|1080p|720p|4k)\b", re.IGNORECASE)
SOURCE_PATTERN = re.compile(r"\b(web[- .]?dl|webrip|bluray|bdrip|remux|hdtv)\b", re.IGNORECASE)
VIDEO_CODEC_PATTERN = re.compile(r"\b(x265|h265|hevc|x264|h264|av1|vp9)\b", re.IGNORECASE)
EFFECT_PATTERN = re.compile(r"\b(dv|dolby[ .-]?vision|hdr10\+|hdr10|hdr|atmos|10bit)\b", re.IGNORECASE)
LEADING_TEAM_PATTERN = re.compile(r"^(?:\[(?P<bracket>[^\]]+)\]|【(?P<cn>[^】]+)】)")
TEAM_PATTERN = re.compile(r"(?:-|【|\[)([A-Za-z0-9&._-]{2,20})(?:】|\])?$")


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
        self.otp_secret = self.settings.moviepilot_otp_secret
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

    def _get_service_manager(self):
        module = importlib.import_module("services.service_manager")
        return module.service_manager

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
            "auto_submit": self.auto_submit,
        }
        if not self.enabled:
            return status

        status["auth_mode"] = "password" if self.username and self.password else "api_key"
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

    @staticmethod
    def _generate_totp(secret: str, for_time: Optional[int] = None, interval: int = 30, digits: int = 6) -> str:
        normalized_secret = (secret or "").replace(" ", "").upper()
        if not normalized_secret:
            raise ValueError("OTP secret 为空")

        try:
            key = base64.b32decode(normalized_secret, casefold=True)
        except binascii.Error as exc:
            raise ValueError("OTP secret 非法") from exc

        timestamp = int(for_time if for_time is not None else time.time())
        counter = struct.pack(">Q", timestamp // interval)
        digest = hmac.new(key, counter, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
        return str(code % (10 ** digits)).zfill(digits)

    def _build_login_form(self) -> Dict[str, str]:
        if not self.username or not self.password:
            raise RuntimeError("MoviePilot 用户名或密码未配置")

        form_data = {
            "username": self.username,
            "password": self.password,
            "grant_type": "password",
        }
        if self.otp_secret:
            form_data["otp_password"] = self._generate_totp(self.otp_secret)
        return form_data

    @staticmethod
    def _merge_reference_profiles(profiles: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
        merged: Dict[str, Optional[str]] = {}
        if not profiles:
            return merged

        for key in ("resolution", "source", "video_codec", "effect", "team"):
            weighted_scores: Dict[str, float] = {}
            for profile in profiles:
                value = profile.get(key)
                if not value:
                    continue
                distance = max(1, int(profile.get("distance") or 1))
                weighted_scores[value] = weighted_scores.get(value, 0.0) + (1 / distance)
            if weighted_scores:
                merged[key] = max(weighted_scores.items(), key=lambda item: item[1])[0]
        return merged

    def _collect_neighbor_profiles(self, video_path: str, season: Optional[int], episode: Optional[int]) -> List[Dict[str, Any]]:
        if not season or not episode:
            return []

        try:
            service_manager = self._get_service_manager()
            health_service = getattr(service_manager, "health_service", None)
            if not health_service:
                return []
            health_service.load_health_data()
            video_files = getattr(health_service, "_health_data", {}).get("videoFiles", {})
        except Exception:
            return []

        decoded_target = unquote(video_path).rstrip("/")
        target_parent = str(Path(decoded_target).parent)
        seen_paths = set()
        neighbors = []

        for candidate_path, candidate_status in video_files.items():
            if not candidate_status.get("hasStrm"):
                continue
            decoded_candidate = unquote(candidate_path).rstrip("/")
            if decoded_candidate == decoded_target or decoded_candidate in seen_paths:
                continue
            seen_paths.add(decoded_candidate)
            if str(Path(decoded_candidate).parent) != target_parent:
                continue

            inferred = self.infer_media_from_path(decoded_candidate)
            candidate_episode = inferred.get("episode")
            candidate_season = inferred.get("season")
            if candidate_season != season or not candidate_episode:
                continue

            distance = abs(candidate_episode - episode)
            if distance == 0 or distance > 3:
                continue

            profile = inferred.get("release_profile") or {}
            if not any(profile.values()):
                continue

            neighbors.append({
                "path": decoded_candidate,
                "episode": candidate_episode,
                "distance": distance,
                "profile": profile,
                **profile,
            })

        neighbors.sort(key=lambda item: (item["distance"], item["episode"]))
        return neighbors[:4]

    async def _get_headers(self) -> Dict[str, str]:
        if not self.username or not self.password:
            if self.api_key:
                return {"X-API-KEY": self.api_key, "User-Agent": "alist-strm/1.0"}
            raise RuntimeError("MoviePilot 用户名或密码未配置")

        if not self._token:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/login/access-token",
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "accept": "application/json",
                    },
                    data=self._build_login_form(),
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
            if response.status_code == 401 and retry_on_unauthorized and self.username and self.password:
                self._token = None
                refreshed_headers = await self._get_headers()
                response = await client.request(method, f"{self.base_url}{path}", headers=refreshed_headers, **kwargs)
            response.raise_for_status()
            if not response.text:
                return None
            return response.json()

    @staticmethod
    def _extract_release_profile(name: str) -> Dict[str, Optional[str]]:
        normalized = (name or "").replace("_", ".")
        resolution = RESOLUTION_PATTERN.search(normalized)
        source = SOURCE_PATTERN.search(normalized)
        video_codec = VIDEO_CODEC_PATTERN.search(normalized)
        effect = EFFECT_PATTERN.search(normalized)
        leading_team = LEADING_TEAM_PATTERN.search(name or "")
        team = leading_team or TEAM_PATTERN.search(normalized)
        return {
            "resolution": resolution.group(1).lower() if resolution else None,
            "source": source.group(1).lower().replace(" ", "").replace(".", "").replace("-", "") if source else None,
            "video_codec": video_codec.group(1).lower() if video_codec else None,
            "effect": effect.group(1).lower().replace(" ", "").replace(".", "").replace("-", "") if effect else None,
            "team": (
                (leading_team.group("bracket") or leading_team.group("cn")).lower()
                if leading_team else team.group(1).lower() if team else None
            ),
        }

    @classmethod
    def infer_media_from_path(cls, video_path: str) -> Dict[str, Any]:
        decoded = unquote(video_path).rstrip("/")
        parts = [part for part in decoded.split("/") if part]
        title = parts[-2] if len(parts) >= 2 else parts[-1] if parts else decoded
        season = None
        filename = parts[-1] if parts else decoded
        episode = None

        for idx in range(len(parts) - 1, -1, -1):
            match = SEASON_PATTERN.search(parts[idx])
            if match:
                season = int(next(group for group in match.groups() if group))
                if idx > 0:
                    title = parts[idx - 1]
                break

        filename_stem = Path(filename).stem
        episode_match = EPISODE_PATTERN.search(filename_stem)
        if episode_match:
            episode = int(next(group for group in episode_match.groups() if group))
        else:
            bracket_match = BRACKET_EPISODE_PATTERN.search(filename_stem)
            if bracket_match:
                episode = int(bracket_match.group(1))
            else:
                candidates = [int(match.group(1)) for match in DASH_EPISODE_PATTERN.finditer(filename_stem)]
                candidates = [value for value in candidates if 0 < value < 200]
                if candidates:
                    episode = candidates[-1]

        year_match = YEAR_PATTERN.search(title)
        year = year_match.group(1) if year_match else None
        normalized_title = YEAR_PATTERN.sub("", title).strip().strip("-_")
        release_profile = cls._extract_release_profile(filename)

        return {
            "title": normalized_title or title,
            "year": year,
            "season": season,
            "episode": episode,
            "media_type": "tv" if season else "movie",
            "filename": filename,
            "release_profile": release_profile,
        }

    def enqueue_missing_source(self, video_path: str, source_reason: str, trigger_path: Optional[str] = None) -> Dict[str, Any]:
        media = self.infer_media_from_path(video_path)
        normalized_path = unquote(video_path)
        neighbor_profiles = self._collect_neighbor_profiles(normalized_path, media["season"], media["episode"])
        reference_profile = self._merge_reference_profiles(neighbor_profiles)

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
            "episode": media["episode"],
            "media_type": media["media_type"],
            "filename": media["filename"],
            "release_profile": media["release_profile"],
            "neighbor_profiles": neighbor_profiles,
            "reference_profile": reference_profile,
            "tmdb_id": None,
            "status": "pending",
            "attempts": 0,
            "created_at": time.time(),
            "updated_at": time.time(),
            "message": None,
            "match_mode": None,
            "selected_resource": None,
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

    async def search_resources(self, item: Dict[str, Any], media_match: Dict[str, Any]) -> List[Dict[str, Any]]:
        tmdb_id = media_match.get("tmdb_id") or media_match.get("tmdbid") or media_match.get("id")
        if not tmdb_id:
            return []

        params = {
            "title": media_match.get("title") or item["title"],
            "year": media_match.get("year") or item.get("year"),
            "season": str(item["season"]) if item.get("season") else None,
        }
        params = {key: value for key, value in params.items() if value not in (None, "", 0)}

        response = await self._request(
            "GET",
            f"/api/v1/search/media/tmdb:{tmdb_id}",
            params=params,
        )

        if isinstance(response, dict):
            data = response.get("data")
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("list", "items", "results", "contexts"):
                    value = data.get(key)
                    if isinstance(value, list):
                        return value
        if isinstance(response, list):
            return response
        return []

    @staticmethod
    def _normalize_profile_value(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return str(value).lower().replace(" ", "").replace(".", "").replace("-", "")

    @classmethod
    def _score_resource_candidate(cls, item: Dict[str, Any], candidate: Dict[str, Any]) -> int:
        meta_info = candidate.get("meta_info") or {}
        torrent_info = candidate.get("torrent_info") or candidate
        score = 0

        target_episode = item.get("episode")
        target_season = item.get("season")
        release_profile = item.get("release_profile") or {}
        reference_profile = item.get("reference_profile") or {}

        begin_season = meta_info.get("begin_season")
        end_season = meta_info.get("end_season")
        if target_season:
            if begin_season == target_season:
                score += 6
            if end_season in (None, 0, target_season):
                score += 2

        episode_list = meta_info.get("episode_list") or []
        begin_episode = meta_info.get("begin_episode")
        end_episode = meta_info.get("end_episode")
        total_episode = meta_info.get("total_episode") or len(episode_list) or 0
        if target_episode:
            if target_episode in episode_list:
                score += 20
                if len(episode_list) == 1:
                    score += 12
            elif begin_episode and end_episode and begin_episode <= target_episode <= end_episode:
                score += 12
                if begin_episode == end_episode == target_episode:
                    score += 8
            elif begin_episode == target_episode or end_episode == target_episode:
                score += 10
            else:
                score -= 18

            if total_episode and total_episode > 3:
                score -= min(total_episode, 24)

        normalized_resolution = cls._normalize_profile_value(release_profile.get("resolution"))
        normalized_source = cls._normalize_profile_value(release_profile.get("source"))
        normalized_codec = cls._normalize_profile_value(release_profile.get("video_codec"))
        normalized_effect = cls._normalize_profile_value(release_profile.get("effect"))
        normalized_team = cls._normalize_profile_value(release_profile.get("team"))

        meta_resolution = cls._normalize_profile_value(meta_info.get("resource_pix"))
        meta_source = cls._normalize_profile_value(meta_info.get("resource_type") or meta_info.get("web_source"))
        meta_codec = cls._normalize_profile_value(meta_info.get("video_encode"))
        meta_effect = cls._normalize_profile_value(meta_info.get("resource_effect"))
        meta_team = cls._normalize_profile_value(meta_info.get("resource_team"))

        if normalized_resolution and meta_resolution and normalized_resolution == meta_resolution:
            score += 8
        if normalized_source and meta_source and normalized_source in meta_source:
            score += 8
        if normalized_codec and meta_codec and normalized_codec in meta_codec:
            score += 8
        if normalized_effect and meta_effect and normalized_effect in meta_effect:
            score += 4
        if normalized_team and meta_team and normalized_team == meta_team:
            score += 10

        reference_resolution = cls._normalize_profile_value(reference_profile.get("resolution"))
        reference_source = cls._normalize_profile_value(reference_profile.get("source"))
        reference_codec = cls._normalize_profile_value(reference_profile.get("video_codec"))
        reference_effect = cls._normalize_profile_value(reference_profile.get("effect"))
        reference_team = cls._normalize_profile_value(reference_profile.get("team"))

        if reference_resolution and meta_resolution and reference_resolution == meta_resolution:
            score += 10
        if reference_source and meta_source and reference_source in meta_source:
            score += 10
        if reference_codec and meta_codec and reference_codec in meta_codec:
            score += 10
        if reference_effect and meta_effect and reference_effect in meta_effect:
            score += 6
        if reference_team and meta_team and reference_team == meta_team:
            score += 14

        seeders = torrent_info.get("seeders") or 0
        size = torrent_info.get("size") or 0
        score += min(int(seeders), 20)
        if size:
            score += min(int(size / (1024 * 1024 * 1024)), 12)

        return score

    async def _download_resource(self, media_match: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
        torrent_info = candidate.get("torrent_info") or candidate
        media_info = candidate.get("media_info") or {
            "title": media_match.get("title"),
            "year": media_match.get("year"),
            "season": media_match.get("season"),
            "tmdb_id": media_match.get("tmdb_id") or media_match.get("tmdbid") or media_match.get("id"),
            "type": media_match.get("type"),
        }
        return await self._request(
            "POST",
            "/api/v1/download/",
            json={"media_in": media_info, "torrent_in": torrent_info},
        )

    async def submit_queue_item(self, item_id: str) -> Dict[str, Any]:
        item = next((entry for entry in self._queue if entry["id"] == item_id), None)
        if not item:
            raise ValueError("订阅项不存在")
        if not self.enabled:
            raise RuntimeError("MoviePilot 未启用")

        item["attempts"] += 1
        item["updated_at"] = time.time()

        try:
            if "reference_profile" not in item or "neighbor_profiles" not in item:
                neighbor_profiles = self._collect_neighbor_profiles(item["video_path"], item.get("season"), item.get("episode"))
                item["neighbor_profiles"] = neighbor_profiles
                item["reference_profile"] = self._merge_reference_profiles(neighbor_profiles)
            matches = await self.search_media(item["title"])
            match = self._pick_best_match(matches or [], item["title"], item.get("year"), item["media_type"])
            if not match:
                item["status"] = "failed"
                item["message"] = "未找到匹配的媒体信息"
                self._save_queue()
                return item

            tmdb_id = match.get("tmdb_id") or match.get("tmdbid") or match.get("id")
            item["tmdb_id"] = int(tmdb_id) if tmdb_id else None

            if item["media_type"] == "tv" and item.get("season") and item.get("episode"):
                resource_candidates = await self.search_resources(item, match)
                scored_candidates = sorted(
                    resource_candidates,
                    key=lambda candidate: self._score_resource_candidate(item, candidate),
                    reverse=True,
                )
                best_candidate = scored_candidates[0] if scored_candidates else None
                best_score = self._score_resource_candidate(item, best_candidate) if best_candidate else -999
                if best_candidate and best_score > 0:
                    response = await self._download_resource(match, best_candidate)
                    success = bool(response and response.get("success"))
                    item["selected_resource"] = (
                        (best_candidate.get("torrent_info") or best_candidate).get("title")
                    )
                    item["match_mode"] = "single_episode_download"
                    item["status"] = "downloading" if success else "failed"
                    item["message"] = response.get("message") if isinstance(response, dict) else None
                    item["updated_at"] = time.time()
                    self._save_queue()
                    return item

            payload = {
                "name": match.get("title") or item["title"],
                "tmdbid": item["tmdb_id"],
                "year": str(match.get("year") or item.get("year") or "") or None,
            }
            if item["media_type"] == "movie":
                payload["type"] = "电影"
            else:
                payload["season"] = item.get("season")

            response = await self._request("POST", "/api/v1/subscribe/", json=payload)
            success = bool(response and response.get("success"))
            item["match_mode"] = "season_subscription"
            item["selected_resource"] = None
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
