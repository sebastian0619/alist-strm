from pathlib import Path

from services.moviepilot_service import MoviePilotService


def test_infer_media_from_path_detects_season_and_year():
    result = MoviePilotService.infer_media_from_path("/动漫/示例剧集 (2025)/Season 1/第03集.mkv")

    assert result["title"] == "示例剧集"
    assert result["year"] == "2025"
    assert result["season"] == 1
    assert result["episode"] == 3
    assert result["media_type"] == "tv"


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


def test_build_login_form_includes_otp_when_secret_is_configured():
    service = MoviePilotService()
    service.username = "user"
    service.password = "pass"
    service.otp_secret = "JBSWY3DPEHPK3PXP"

    form = service._build_login_form()

    assert form["username"] == "user"
    assert form["password"] == "pass"
    assert form["grant_type"] == "password"
    assert len(form["otp_password"]) == 6
    assert form["otp_password"].isdigit()


def test_get_headers_falls_back_to_api_key_when_credentials_missing(tmp_path):
    service = MoviePilotService()
    service.queue_file = Path(tmp_path) / "moviepilot_missing_sources.json"
    service.api_key = "test-api-key"
    service.username = ""
    service.password = ""
    service.otp_secret = ""
    service._token = None
    service._get_mp_token = _raise_if_called  # type: ignore[attr-defined]

    import asyncio

    headers = asyncio.run(service._get_headers())

    assert headers["X-API-KEY"] == "test-api-key"
