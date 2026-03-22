import asyncio
import os
from pathlib import Path

from services.archive_service import ArchiveService


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
