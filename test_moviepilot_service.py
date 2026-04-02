from pathlib import Path

from services.moviepilot_service import MoviePilotService


def test_infer_media_from_path_detects_season_and_year():
    result = MoviePilotService.infer_media_from_path("/动漫/示例剧集 (2025)/Season 1/第03集.mkv")

    assert result == {
        "title": "示例剧集",
        "year": "2025",
        "season": 1,
        "media_type": "tv",
    }


def test_enqueue_missing_source_deduplicates_pending_items(tmp_path):
    service = MoviePilotService()
    service.queue_file = Path(tmp_path) / "moviepilot_missing_sources.json"
    service._queue = []

    first = service.enqueue_missing_source("/电影/示例电影 (2026)/示例电影 (2026).mkv", "manual")
    second = service.enqueue_missing_source("/电影/示例电影 (2026)/示例电影 (2026).mkv", "manual")

    assert first["id"] == second["id"]
    assert len(service.get_queue()) == 1


async def _raise_if_called():
    raise AssertionError("使用 API Key 时不应请求 token")


def test_get_headers_prefers_api_key(tmp_path):
    service = MoviePilotService()
    service.queue_file = Path(tmp_path) / "moviepilot_missing_sources.json"
    service.api_key = "test-api-key"
    service.username = ""
    service.password = ""
    service._token = None
    service._get_mp_token = _raise_if_called  # type: ignore[attr-defined]

    import asyncio

    headers = asyncio.run(service._get_headers())

    assert headers["X-API-KEY"] == "test-api-key"
