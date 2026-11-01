"""回归：合并格式取直链时不得返回无音轨的视频流（第 8 轮自主排查）。

真实缺陷：前端的格式列表首位与默认 format_id 都是合并选择器
`bestvideo+bestaudio/best`。yt-dlp 在合并选择器下不会产出单一的 `info["url"]`，
`requested_formats` 里分别是纯视频流与纯音频流；原实现直接取 `requested_formats[0]`，
返回的是**无音轨视频**，前端内联预览（VideoResult.openPreview → /api/direct-url）
有画面没声音。

修复：合并格式下优先在 `info["formats"]` 中挑同时含视频+音频的渐进式格式，
取不到再退回原行为（保持既有兜底，不新增失败路径）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest  # noqa: E402

import downloader  # noqa: E402


class _FakeYDL:
    """替身 YoutubeDL：只回放预设的 info，不做任何网络请求。"""

    def __init__(self, info):
        self._info = info

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        return self._info


def _make_downloader():
    # 绕过 __init__：避免创建 downloads 目录与探测 ffmpeg（static_ffmpeg 可能触发下载）
    return downloader.VideoDownloader.__new__(downloader.VideoDownloader)


def _patch_info(monkeypatch, info):
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", lambda opts: _FakeYDL(info))


def test_merged_format_returns_progressive_url_with_audio(monkeypatch):
    """合并格式：必须返回带音轨的渐进式直链，而不是 requested_formats[0] 的纯视频流。"""
    progressive_720 = {
        "format_id": "22",
        "url": "https://cdn.test/720.mp4",
        "vcodec": "avc1",
        "acodec": "mp4a",
        "height": 720,
        "ext": "mp4",
        "filesize": 12_000_000,
    }
    info = {
        "title": "t",
        # 合并选择器下没有顶层 url
        "url": None,
        "requested_formats": [
            {
                "format_id": "137",
                "url": "https://cdn.test/1080-video-only.mp4",
                "vcodec": "avc1",
                "acodec": "none",
                "height": 1080,
            },
            {
                "format_id": "140",
                "url": "https://cdn.test/audio.m4a",
                "vcodec": "none",
                "acodec": "mp4a",
            },
        ],
        "formats": [
            # 纯视频流：绝不能选中
            {
                "format_id": "137",
                "url": "https://cdn.test/1080-video-only.mp4",
                "vcodec": "avc1",
                "acodec": "none",
                "height": 1080,
                "ext": "mp4",
            },
            # 纯音频流：同样不能单独作为预览直链
            {
                "format_id": "140",
                "url": "https://cdn.test/audio.m4a",
                "vcodec": "none",
                "acodec": "mp4a",
                "ext": "m4a",
            },
            progressive_720,
        ],
    }
    _patch_info(monkeypatch, info)

    result = _make_downloader().get_direct_url(
        "https://x.test/v", "bestvideo+bestaudio/best"
    )

    assert result["direct_url"] == "https://cdn.test/720.mp4"
    assert result["ext"] == "mp4"
    assert result["filesize"] == 12_000_000


def test_merged_format_picks_highest_progressive(monkeypatch):
    """多个渐进式格式时取分辨率最高的（同分辨率优先 mp4）。"""
    info = {
        "url": None,
        "requested_formats": [{"url": "https://cdn.test/v.mp4"}],
        "formats": [
            {
                "url": "https://cdn.test/360.mp4",
                "vcodec": "avc1",
                "acodec": "mp4a",
                "height": 360,
                "ext": "mp4",
            },
            {
                "url": "https://cdn.test/720.webm",
                "vcodec": "vp9",
                "acodec": "opus",
                "height": 720,
                "ext": "webm",
            },
            {
                "url": "https://cdn.test/720.mp4",
                "vcodec": "avc1",
                "acodec": "mp4a",
                "height": 720,
                "ext": "mp4",
            },
        ],
    }
    _patch_info(monkeypatch, info)

    result = _make_downloader().get_direct_url(
        "https://x.test/v", "bestvideo+bestaudio/best"
    )
    assert result["direct_url"] == "https://cdn.test/720.mp4"


def test_merged_format_without_progressive_falls_back(monkeypatch):
    """没有任何渐进式格式时，保持原有兜底（requested_formats[0]），不得直接报错。"""
    info = {
        "url": None,
        "requested_formats": [{"url": "https://cdn.test/video-only.mp4"}],
        "formats": [
            {
                "url": "https://cdn.test/video-only.mp4",
                "vcodec": "avc1",
                "acodec": "none",
                "height": 1080,
            }
        ],
    }
    _patch_info(monkeypatch, info)

    result = _make_downloader().get_direct_url(
        "https://x.test/v", "bestvideo+bestaudio/best"
    )
    assert result["direct_url"] == "https://cdn.test/video-only.mp4"


def test_single_format_returns_top_level_url(monkeypatch):
    """非合并格式（含用户手动选的纯视频/纯音频）仍以 info["url"] 为准，不受修复影响。"""
    info = {
        "url": "https://cdn.test/137.mp4",
        "ext": "mp4",
        "filesize": 100,
        "title": "t",
        "formats": [
            {
                "url": "https://cdn.test/progressive.mp4",
                "vcodec": "avc1",
                "acodec": "mp4a",
                "height": 720,
                "ext": "mp4",
            }
        ],
    }
    _patch_info(monkeypatch, info)

    result = _make_downloader().get_direct_url("https://x.test/v", "137")
    assert result["direct_url"] == "https://cdn.test/137.mp4"
    assert result["filesize"] == 100


def test_missing_url_still_raises(monkeypatch):
    """既无顶层 url 也无 requested_formats 时仍按原约定报错。"""
    _patch_info(monkeypatch, {"title": "t", "formats": []})

    with pytest.raises(ValueError):
        _make_downloader().get_direct_url("https://x.test/v", "best")
