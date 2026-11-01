"""回归：抖音下载模式判定不能用 format_id 子串匹配（第 10 轮自主排查）。

`/api/download` 原实现用 `"audio" in req.format_id` 判定抖音下载模式。
但前端默认格式 `bestvideo+bestaudio/best`（也是后端 `DownloadRequest` 的默认值）
同样含 "audio" 子串，于是用户点「下载视频」实际拿到的是一个 mp3。

历史记录重新下载正是这条路径：旧记录没有 `extra.format_id`，
`HistoryDrawer` 调 `enqueue(url, '', title)`，前端回退到该默认合并选择器。

修复：仅当 format_id 是纯音频选择器（audio / audio_only / bestaudio /
douyin_audio）时才走音频模式，其余一律按视频处理。
"""
import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

DOUYIN_URL = "https://www.douyin.com/video/7001234"


@pytest.fixture()
def douyin_download_spy(tmp_path):
    """替换抖音下载实现：记录 mode，并返回真实存在的临时文件。

    同时放宽下载限流器：参数化用例会连打多次，默认 5 次/60s 会触发 429。
    """
    fake_file = tmp_path / "out.mp4"
    fake_file.write_bytes(b"fake-media")

    captured = {}

    def fake_download(url, mode="video"):
        captured["url"] = url
        captured["mode"] = mode
        return {"filepath": str(fake_file), "filename": "out.mp4"}

    import main

    with mock.patch.object(main, "_validate_public_url", side_effect=lambda u: u), \
            mock.patch.object(main.douyin_parser, "download", side_effect=fake_download), \
            mock.patch.object(
                main,
                "_download_limiter",
                main.RateLimiter(max_requests=1000, window_seconds=60),
            ):
        yield captured


def _post_download(payload):
    from fastapi.testclient import TestClient
    import main

    with TestClient(main.app) as client:
        return client.post("/api/download", json=payload)


@pytest.mark.parametrize(
    "format_id",
    [
        "bestvideo+bestaudio/best",  # 前后端默认合并选择器（缺陷主路径）
        "douyin_nowm",               # 抖音无水印视频
        "video",
    ],
)
def test_douyin_video_selector_uses_video_mode(format_id, douyin_download_spy):
    """视频类选择器（尤其默认合并格式）必须走视频模式，不能产出 mp3。"""
    resp = _post_download({"url": DOUYIN_URL, "format_id": format_id})
    assert resp.status_code == 200, resp.text
    assert douyin_download_spy["mode"] == "video"


@pytest.mark.parametrize(
    "format_id",
    ["audio", "audio_only", "bestaudio", "douyin_audio", " Audio "],
)
def test_douyin_audio_selector_uses_audio_mode(format_id, douyin_download_spy):
    """纯音频选择器必须走音频模式（含大小写与首尾空白差异）。"""
    resp = _post_download({"url": DOUYIN_URL, "format_id": format_id})
    assert resp.status_code == 200, resp.text
    assert douyin_download_spy["mode"] == "audio"


def test_douyin_download_without_format_uses_video_mode(douyin_download_spy):
    """未传 format_id 时走 DownloadRequest 默认值，同样必须判为视频。"""
    resp = _post_download({"url": DOUYIN_URL})
    assert resp.status_code == 200, resp.text
    assert douyin_download_spy["mode"] == "video"
