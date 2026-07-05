import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock

from services.archive_service import ArchiveService
from services.lifecycle_service import LifecycleService
from services.state_db import StateDatabaseService


def test_archive_target_paths_season():
    service = ArchiveService()
    service.settings.alist_scan_path = "/123/video"
    candidate = service._archive_target_paths("/123/video/电视剧/Season 1/第一集.mkv")

    assert candidate is not None
    assert candidate["relative"] == "电视剧/Season 1/第一集.mkv"
    assert candidate["season_dir"] is True
    assert candidate["archive_path"].startswith("/123/video/archive")
    assert candidate["cloud_path"].startswith("/123/video/电视剧")


def test_add_to_pending_deletion_records_move_success(tmp_path):
    service = ArchiveService()
    path = tmp_path / "testfile.strm"
    path.write_text("dummy")

    service._pending_deletions = []
    service._get_service_manager = lambda: type(
        "Manager",
        (),
        {
            "telegram_service": type("TG", (), {"send_message": staticmethod(lambda *a, **k: None)})()
        },
    )()
    service._add_to_pending_deletion(
        path,
        cloud_path="/123/video/电视剧/Season 1/第一集.mkv",
        archive_path="/123/video/archive/电视剧/Season 1/第一集.mkv",
        move_success=True
    )

    assert len(service._pending_deletions) == 1
    entry = service._pending_deletions[0]
    assert entry["cloud_path"] == "/123/video/电视剧/Season 1/第一集.mkv"
    assert entry["archive_path"].endswith("archive/电视剧/Season 1/第一集.mkv")
    assert entry["move_success"] is True


def test_build_archive_paths_from_relative_preserves_joining():
    service = ArchiveService()
    service.settings.archive_source_alist = "/123/video"
    service.settings.archive_target_root = "/123/video/archive"

    path_info = service._build_archive_paths_from_relative(Path("电视剧/Season 1/第一集.mkv"))

    assert path_info["source_alist_path"] == "123/video/电视剧/Season 1/第一集.mkv"
    assert path_info["dest_alist_path"] == "123/video/archive/电视剧/Season 1/第一集.mkv"
    assert str(path_info["dest_path"]).endswith("/123/video/archive/电视剧/Season 1/第一集.mkv")


def test_season_archive_candidate_returns_season_root(tmp_path):
    service = ArchiveService()
    media_root = tmp_path / "tv"
    season_root = media_root / "电视剧" / "Season 1"
    episode_dir = season_root / "extras"
    episode_dir.mkdir(parents=True)

    candidate = service._season_archive_candidate(episode_dir, media_root)

    assert candidate == season_root


def test_delete_file_ignores_missing_children_during_directory_delete(tmp_path, monkeypatch):
    service = ArchiveService()
    target_dir = tmp_path / "show"
    target_dir.mkdir()
    flaky_file = target_dir / "episode-mediainfo.json"
    normal_file = target_dir / "episode.nfo"
    flaky_file.write_text("x")
    normal_file.write_text("y")

    original_unlink = Path.unlink

    def flaky_unlink(self, *args, **kwargs):
        if self == flaky_file:
            if self.exists():
                original_unlink(self, *args, **kwargs)
            raise FileNotFoundError(self.name)
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)

    result = asyncio.run(service._delete_file(target_dir))

    assert result is True
    assert not target_dir.exists()


def test_revive_series_directory_moves_paths_and_updates_state(tmp_path, monkeypatch):
    source_root = tmp_path / "video"
    source_dir = source_root / "动漫" / "完结动漫" / "示例剧 (2025)" / "Season 1"
    source_dir.mkdir(parents=True)
    episode_file = source_dir / "示例剧.S01E01.mkv"
    episode_file.write_text("video")

    output_dir = tmp_path / "Strm"
    db = StateDatabaseService()
    db.db_path = str(tmp_path / "app.db")
    lifecycle = LifecycleService()

    series_state = lifecycle.sync_series_state(
        db,
        local_path=str(source_dir),
        remote_path="/123/video/archive/动漫/完结动漫/示例剧 (2025)/Season 1",
        strm_path=str(output_dir / "动漫" / "完结动漫" / "示例剧 (2025)" / "Season 1"),
        tmdb_status="Returning Series",
        local_exists=True,
        reason="seed_state",
    )

    service = ArchiveService()
    service.settings.archive_source_root = str(source_root)
    service.settings.archive_source_alist = "/123/video"
    service.settings.alist_scan_path = "/123/video"
    service._pending_deletions = [{
        "path": source_dir,
        "cloud_path": "/123/video/archive/动漫/完结动漫/示例剧 (2025)/Season 1",
        "archive_path": "/123/video/archive/动漫/完结动漫/示例剧 (2025)/Season 1",
        "delete_time": 0,
        "move_success": True,
    }]
    service._save_pending_deletions = lambda: None

    fake_strm_service = type("StrmService", (), {"settings": type("Settings", (), {"output_dir": str(output_dir)})()})()
    fake_manager = type(
        "Manager",
        (),
        {
            "state_db": db,
            "lifecycle_service": lifecycle,
            "strm_service": fake_strm_service,
            "health_service": type("Health", (), {"remove_strm_file": staticmethod(lambda *a, **k: None)})(),
        },
    )()
    service._get_service_manager = lambda: fake_manager
    service.alist_client.path_exists = AsyncMock(return_value=False)
    service.alist_client.move_directory = AsyncMock(return_value=True)
    service.generate_strm_for_target = AsyncMock(return_value=True)

    files_info = [{
        "path": episode_file,
        "size": episode_file.stat().st_size,
        "relative_path": Path("Season 1") / episode_file.name,
    }]

    result = asyncio.run(
        service._revive_series_directory(
            source_dir,
            "/123/video/archive/动漫/完结动漫/示例剧 (2025)/Season 1",
            "/123/video/archive/动漫/完结动漫/示例剧 (2025)/Season 1",
            files_info,
        )
    )

    revived_dir = source_root / "动漫" / "连载动漫" / "示例剧 (2025)" / "Season 1"
    row = db.find_series_state_by_identity(normalized_title="示例剧", year="2025", media_type="tv")

    assert result["success"] is True
    assert revived_dir.exists()
    assert not source_dir.exists()
    assert row is not None
    assert row["state"] == "airing_local"
    assert row["current_local_path"] == str(revived_dir)
    assert service._pending_deletions == []
