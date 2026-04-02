import asyncio
from pathlib import Path
from types import SimpleNamespace

from routes import health
from services.strm_health_service import StrmHealthService


class FakeHealthService:
    def __init__(self, target_path):
        self.target_path = target_path
        self.removed_strm_paths = []
        self.removed_video_paths = []
        self.added = []
        self.saved = False
        self.updated_videos = []

    def get_strm_status(self, path):
        return {"targetPath": self.target_path}

    def remove_strm_file(self, path):
        self.removed_strm_paths.append(path)

    def remove_video_file(self, path):
        self.removed_video_paths.append(path)

    def add_strm_file(self, strm_path, video_path):
        self.added.append((strm_path, video_path))

    def save_health_data(self):
        self.saved = True

    def update_video_status(self, path, status):
        self.updated_videos.append((path, status))


class FakeMoviePilotService:
    def __init__(self, enabled=True, auto_submit=False):
        self.enabled = enabled
        self.auto_submit = auto_submit
        self.enqueued = []
        self.submitted = []

    def enqueue_missing_source(self, video_path, source_reason, trigger_path=None):
        item = {
            "id": f"item-{len(self.enqueued)}",
            "video_path": video_path,
            "reason": source_reason,
            "trigger_path": trigger_path,
            "status": "pending",
        }
        self.enqueued.append(item)
        return item

    async def submit_queue_item(self, item_id):
        self.submitted.append(item_id)
        return {
            "id": item_id,
            "status": "subscribed",
        }


def test_remove_video_file_handles_encoded_and_decoded_paths():
    service = StrmHealthService()
    service._health_data = {
        "lastFullScanTime": 0,
        "strmFiles": {},
        "videoFiles": {
            "/动漫/剧集/第01集.mkv": {"hasStrm": False},
            "%2F动漫%2F剧集%2F第01集.mkv": {"hasStrm": False},
        },
    }
    service._is_loaded = True

    service.remove_video_file("/动漫/剧集/第01集.mkv")

    assert service._health_data["videoFiles"] == {}


def test_cleanup_invalid_strm_entries_rebuilds_when_source_still_exists(tmp_path, monkeypatch):
    invalid_strm = tmp_path / "show" / "ep01@remote(网盘).strm"
    invalid_strm.parent.mkdir(parents=True)
    invalid_strm.write_text("http://old")

    fake_health = FakeHealthService("/动漫/剧集/第01集.mkv")
    fake_manager = SimpleNamespace(
        health_service=fake_health,
        strm_service=SimpleNamespace(
            settings=SimpleNamespace(
                output_dir=str(tmp_path / "output"),
                alist_url="http://alist:5244",
            )
        ),
        moviepilot_service=FakeMoviePilotService(enabled=True, auto_submit=False),
    )

    monkeypatch.setattr(health, "service_manager", fake_manager)

    async def fake_exists(path):
        return True

    monkeypatch.setattr(health, "check_alist_file_exists", fake_exists)

    result = asyncio.run(health._cleanup_invalid_strm_entries([str(invalid_strm)]))

    assert result["cleaned_paths"] == [str(invalid_strm)]
    assert result["failed_items"] == []
    assert len(result["recovered_items"]) == 1
    rebuilt_path = Path(result["recovered_items"][0]["strm_path"])
    assert rebuilt_path.exists()
    assert fake_health.removed_strm_paths == [str(invalid_strm)]
    assert fake_health.added[0][1] == "/动漫/剧集/第01集.mkv"
    assert fake_health.saved is True


def test_cleanup_invalid_strm_entries_drops_missing_source_from_video_status(tmp_path, monkeypatch):
    invalid_strm = tmp_path / "show" / "ep02@remote(网盘).strm"
    invalid_strm.parent.mkdir(parents=True)
    invalid_strm.write_text("http://old")

    fake_health = FakeHealthService("/动漫/剧集/第02集.mkv")
    fake_manager = SimpleNamespace(
        health_service=fake_health,
        strm_service=SimpleNamespace(
            settings=SimpleNamespace(
                output_dir=str(tmp_path / "output"),
                alist_url="http://alist:5244",
            )
        ),
        moviepilot_service=FakeMoviePilotService(enabled=True, auto_submit=False),
    )

    monkeypatch.setattr(health, "service_manager", fake_manager)

    async def fake_exists(path):
        return False

    monkeypatch.setattr(health, "check_alist_file_exists", fake_exists)

    result = asyncio.run(health._cleanup_invalid_strm_entries([str(invalid_strm)]))

    assert result["cleaned_paths"] == [str(invalid_strm)]
    assert result["recovered_items"] == []
    assert result["removed_source_items"] == ["/动漫/剧集/第02集.mkv"]
    assert result["subscription_items"][0]["video_path"] == "/动漫/剧集/第02集.mkv"
    assert fake_health.removed_video_paths
    assert fake_health.saved is True


def test_cleanup_invalid_strm_entries_auto_submits_moviepilot_queue(tmp_path, monkeypatch):
    invalid_strm = tmp_path / "show" / "ep03@remote(网盘).strm"
    invalid_strm.parent.mkdir(parents=True)
    invalid_strm.write_text("http://old")

    fake_health = FakeHealthService("/动漫/剧集/Season 1/第03集.mkv")
    fake_moviepilot = FakeMoviePilotService(enabled=True, auto_submit=True)
    fake_manager = SimpleNamespace(
        health_service=fake_health,
        strm_service=SimpleNamespace(
            settings=SimpleNamespace(
                output_dir=str(tmp_path / "output"),
                alist_url="http://alist:5244",
            )
        ),
        moviepilot_service=fake_moviepilot,
    )

    monkeypatch.setattr(health, "service_manager", fake_manager)

    async def fake_exists(path):
        return False

    monkeypatch.setattr(health, "check_alist_file_exists", fake_exists)

    result = asyncio.run(health._cleanup_invalid_strm_entries([str(invalid_strm)]))

    assert fake_moviepilot.submitted == ["item-0"]
    assert result["subscription_items"] == [{"id": "item-0", "status": "subscribed"}]


def test_infer_repair_scope_root_prefers_season_directory():
    scope = health._infer_repair_scope_root('/动漫/剧集/Season 1/第01集.mkv')

    assert scope == '/动漫/剧集/Season 1'


def test_infer_repair_scope_root_falls_back_to_parent_directory():
    scope = health._infer_repair_scope_root('/电影/示例电影 (2026)/示例电影 (2026).mkv')

    assert scope == '/电影/示例电影 (2026)'
