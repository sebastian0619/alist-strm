from services.emby_service import EmbyService


def test_path_conversion():
    service = EmbyService()
    service.strm_root_path = "/mnt/strm"
    service.emby_root_path = "/mnt/media"

    cases = [
        ("/mnt/strm/电影/测试电影 (2023)/测试电影.strm", "/mnt/media/电影/测试电影 (2023)/测试电影.strm"),
        ("mnt/strm/电视剧/测试剧集/Season 1/测试剧集 - S01E01.strm", "/mnt/media/电视剧/测试剧集/Season 1/测试剧集 - S01E01.strm"),
        ("\\mnt\\strm\\动漫\\测试动漫\\Season 1\\测试动漫 - S01E01.strm", "/mnt/media/动漫/测试动漫/Season 1/测试动漫 - S01E01.strm"),
        ("/mnt/user/media/测试媒体/测试电影 (2020).strm", "/mnt/user/media/测试媒体/测试电影 (2020).strm"),
        ("/completely/different/path/test.strm", "/completely/different/path/test.strm"),
    ]

    for src, expected in cases:
        assert service.convert_to_emby_path(src) == expected
