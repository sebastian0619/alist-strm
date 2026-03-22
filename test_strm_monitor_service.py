import asyncio
from pathlib import Path
from types import SimpleNamespace

from services.strm_monitor_service import StrmFileHandler


class FakeHealthService:
    def __init__(self):
        self.status = {}
        self.removed = []
        self.saved = 0

    def get_strm_status(self, path):
        return self.status.get(path, {})

    def remove_strm_file(self, path):
        self.removed.append(path)
        self.status.pop(path, None)

    def add_strm_file(self, path, target):
        self.status[path] = {"targetPath": target}

    def save_health_data(self):
        self.saved += 1


class FakeClient:
    instances = []

    def __init__(self, base_url, token):
        self.base_url = base_url
        self.token = token
        self.moves = []
        self.closed = False
        FakeClient.instances.append(self)

    async def move_file(self, src, dst):
        self.moves.append((src, dst))
        return True

    async def move_directory(self, src, dst):
        self.moves.append((src, dst))
        return True

    async def close(self):
        self.closed = True


def build_handler(tmp_path):
    output_dir = tmp_path / "strm"
    output_dir.mkdir()
    settings = SimpleNamespace(
        output_dir=str(output_dir),
        alist_url="http://alist.local",
        alist_token="",
        alist_scan_path="/library",
        encode=True,
        use_external_url=False,
        alist_external_url="",
    )
    strm_service = SimpleNamespace(settings=settings)
    return StrmFileHandler(strm_service, asyncio.get_running_loop())


async def test_handle_move_updates_remote_and_health(monkeypatch, tmp_path):
    from services import strm_monitor_service

    handler = build_handler(tmp_path)
    health = FakeHealthService()
    service_manager = SimpleNamespace(health_service=health)
    monkeypatch.setattr(strm_monitor_service, "AlistClient", FakeClient)
    monkeypatch.setattr(handler, "_get_service_manager", lambda: service_manager)

    dest_rel = "电影/新名字@remote(网盘).strm"
    dest_abs = Path(handler.strm_service.settings.output_dir) / dest_rel
    dest_abs.parent.mkdir(parents=True, exist_ok=True)
    dest_abs.write_text("http://alist.local/d/library/%E7%94%B5%E5%BD%B1/%E6%97%A7%E5%90%8D%E5%AD%97.mkv", encoding="utf-8")

    src_abs = str(Path(handler.strm_service.settings.output_dir) / "电影/旧名字@remote(网盘).strm")
    await handler._handle_move("电影/旧名字@remote(网盘).strm", dest_rel)

    assert FakeClient.instances[-1].moves == [("/library/电影/旧名字.mkv", "/library/电影/新名字")]
    assert dest_abs.read_text(encoding="utf-8") == "http://alist.local/d/library/%E7%94%B5%E5%BD%B1/%E6%96%B0%E5%90%8D%E5%AD%97"
    assert src_abs in health.removed
    assert health.status[str(dest_abs)]["targetPath"] == "/library/电影/新名字"
    assert health.saved == 1
    assert FakeClient.instances[-1].closed is True


async def test_handle_delete_uses_health_cache_when_file_is_missing(monkeypatch, tmp_path):
    from services import strm_monitor_service

    handler = build_handler(tmp_path)
    health = FakeHealthService()
    strm_abs = str(Path(handler.strm_service.settings.output_dir) / "电影/旧名字@remote(网盘).strm")
    health.status[strm_abs] = {"targetPath": "/library/电影/旧名字.mkv"}
    service_manager = SimpleNamespace(health_service=health)
    monkeypatch.setattr(strm_monitor_service, "AlistClient", FakeClient)
    monkeypatch.setattr(handler, "_get_service_manager", lambda: service_manager)

    await handler._handle_delete("电影/旧名字@remote(网盘).strm")

    assert FakeClient.instances[-1].moves == [("/library/电影/旧名字.mkv", "/library/archive/电影/旧名字.mkv")]
    assert strm_abs in health.removed
    assert health.saved == 1
    assert FakeClient.instances[-1].closed is True
