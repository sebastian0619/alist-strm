from services.lifecycle_service import LifecycleService
from services.state_db import StateDatabaseService


def test_state_db_upserts_series_and_transition(tmp_path):
    service = StateDatabaseService()
    service.db_path = str(tmp_path / "app.db")

    first = service.upsert_series_state(
        normalized_title="示例剧",
        title="示例剧",
        year="2025",
        media_type="tv",
        state="airing_local",
        current_local_path="/processroot/video/动漫/连载动漫/示例剧 (2025)",
    )
    second = service.upsert_series_state(
        normalized_title="示例剧",
        title="示例剧",
        year="2025",
        media_type="tv",
        state="archived_pending_delete",
        current_local_path="/processroot/video/动漫/完结动漫/示例剧 (2025)",
    )

    transitions = []
    with service.connection() as conn:
        rows = conn.execute("SELECT * FROM state_transitions ORDER BY id ASC").fetchall()
        transitions = [dict(row) for row in rows]

    assert first["id"] == second["id"]
    assert second["state"] == "archived_pending_delete"
    assert transitions[-1]["to_state"] == "archived_pending_delete"


def test_lifecycle_service_infers_revived_state():
    lifecycle = LifecycleService()

    state = lifecycle.infer_state(
        local_path="/processroot/video/动漫/完结动漫/示例剧 (2025)",
        remote_path="/123/video/动漫/完结动漫/示例剧 (2025)",
        tmdb_status="Returning Series",
        local_exists=False,
    )

    assert state == "revived"


def test_lifecycle_service_builds_revival_paths():
    lifecycle = LifecycleService()

    paths = lifecycle.build_revival_paths(
        local_path="/processroot/video/动漫/完结动漫/示例剧 (2025)/Season 1",
        remote_path="/123/video/archive/动漫/完结动漫/示例剧 (2025)/Season 1",
        strm_root_path="/processroot/Strm/动漫/完结动漫/示例剧 (2025)/Season 1",
    )

    assert paths["target_local_path"] == "/processroot/video/动漫/连载动漫/示例剧 (2025)/Season 1"
    assert paths["target_remote_path"] == "/123/video/动漫/连载动漫/示例剧 (2025)/Season 1"
    assert paths["target_strm_path"] == "/processroot/Strm/动漫/连载动漫/示例剧 (2025)/Season 1"


def test_state_db_persists_pending_deletions_and_missing_tasks(tmp_path):
    service = StateDatabaseService()
    service.db_path = str(tmp_path / "app.db")
    service.initialize()

    service.upsert_pending_deletion({
        "path": "/tmp/source/show",
        "cloud_path": "/local/video/show",
        "archive_path": "/123/video/show",
        "delete_time": 1234567890,
        "move_success": True,
    })
    service.upsert_missing_source_task({
        "id": "mp_1",
        "video_path": "/123/video/动漫/示例剧 (2025)/Season 1/第03集.mkv",
        "status": "pending",
        "title": "示例剧",
        "year": "2025",
        "season": 1,
        "episode": 3,
        "media_type": "tv",
        "filename": "第03集.mkv",
        "release_profile": {"resolution": "1080p"},
        "neighbor_profiles": [],
        "reference_profile": {"resolution": "1080p"},
    })

    pending = service.get_pending_deletions()
    tasks = service.get_missing_source_tasks()

    assert pending[0]["archive_path"] == "/123/video/show"
    assert tasks[0]["reference_profile"]["resolution"] == "1080p"


def test_state_db_can_find_series_by_identity(tmp_path):
    service = StateDatabaseService()
    service.db_path = str(tmp_path / "app.db")

    service.upsert_series_state(
        normalized_title="示例剧",
        title="示例剧",
        year="2025",
        media_type="tv",
        state="airing_local",
        current_local_path="/processroot/video/动漫/连载动漫/示例剧 (2025)",
    )

    row = service.find_series_state_by_identity(
        normalized_title="示例剧",
        year="2025",
        media_type="tv",
    )

    assert row is not None
    assert row["current_local_path"].endswith("/连载动漫/示例剧 (2025)")


def test_lifecycle_service_analyzes_duplicate_library_conflicts(tmp_path):
    source_root = tmp_path / "video"
    ended_root = source_root / "动漫" / "完结动漫"
    airing_root = source_root / "动漫" / "连载动漫"
    (ended_root / "示例剧 (2025)").mkdir(parents=True)
    (airing_root / "示例剧 (2025)").mkdir(parents=True)

    service = StateDatabaseService()
    service.db_path = str(tmp_path / "app.db")
    service.upsert_series_state(
        normalized_title="示例剧",
        title="示例剧",
        year="2025",
        media_type="tv",
        state="airing_local",
        last_tmdb_status="Returning Series",
        current_local_path=str(airing_root / "示例剧 (2025)"),
    )

    lifecycle = LifecycleService()
    report = lifecycle.analyze_library_alignment(
        service,
        scan_root=str(source_root),
    )

    assert report["conflict_count"] == 1
    conflict = report["conflicts"][0]
    assert conflict["issue_type"] == "duplicate_across_libraries"
    assert conflict["recommended_role"] == "airing"
    assert len(conflict["items"]) == 2
