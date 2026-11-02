"""回归：平台域名严格匹配 + 下载配额清理的并发竞态容错。

缺陷一（summarizer）：`_is_douyin_url` / `_is_bilibili_url` 用 `"douyin.com" in url`
这类子串判断，`https://douyin.com.evil.com/video/1`、`https://mydouyin.com/x` 都会被
当成抖音，走抖音专用解析（终点域名校验失败）后直接返回「无字幕」，本应交给 yt-dlp
通用流程；B 站同理，只要 URL 里出现 `bilibili.com` 且带 BV 号，就会拿到另一个视频的字幕。

缺陷二（downloader）：`_enforce_quota` 直接 `sum(getsize)` / `sort(getmtime)`，
并发下载在本函数执行期间把 `.part` rename 成正式文件（douyin / yt-dlp 都会）时，
getsize 抛 FileNotFoundError，整个下载请求随之失败。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import downloader
import summarizer


# ---------- 域名严格匹配 ----------

@pytest.mark.parametrize("url", [
    "https://www.douyin.com/video/7123456789012345678",
    "https://douyin.com/video/1",
    "https://v.douyin.com/iRNBho6u/",
    "https://www.iesdouyin.com/share/video/7123456789012345678/",
])
def test_is_douyin_url_accepts_real_hosts(url):
    assert summarizer._is_douyin_url(url) is True


@pytest.mark.parametrize("url", [
    "https://douyin.com.evil.com/video/1",
    "https://mydouyin.com/video/1",
    "https://evil.com/?u=https://www.douyin.com/video/1",
    "https://www.douyin.com.cn.example.org/v/1",
])
def test_is_douyin_url_rejects_substring_spoofing(url):
    assert summarizer._is_douyin_url(url) is False


@pytest.mark.parametrize("url", [
    "https://www.bilibili.com/video/BV1xx411c7mD",
    "https://b23.tv/abcdefg",
])
def test_is_bilibili_url_accepts_real_hosts(url):
    assert summarizer._is_bilibili_url(url) is True


@pytest.mark.parametrize("url", [
    "https://notbilibili.com/video/BV1xx411c7mD",
    "https://bilibili.com.evil.com/video/BV1xx411c7mD",
    "https://evil.com/?ref=bilibili.com&v=BV1xx411c7mD",
])
def test_is_bilibili_url_rejects_substring_spoofing(url):
    assert summarizer._is_bilibili_url(url) is False


def test_extract_does_not_route_spoofed_douyin_host(monkeypatch):
    """伪装域名必须落到 yt-dlp 通用流程，而不是被抖音专用解析短路成「无字幕」。"""
    calls = {"douyin": 0, "generic": 0}

    def fake_douyin(url):
        calls["douyin"] += 1
        return None

    def fake_generic(self, url):
        calls["generic"] += 1
        return {}

    monkeypatch.setattr(summarizer, "_parse_douyin_video_info", fake_douyin)
    monkeypatch.setattr(summarizer.SubtitleExtractor, "_get_video_info", fake_generic)

    result = summarizer.SubtitleExtractor().extract("https://douyin.com.evil.com/video/1")

    assert calls["douyin"] == 0
    assert calls["generic"] == 1
    assert result["has_subtitle"] is False


def test_extract_still_uses_douyin_desc_for_real_host(monkeypatch):
    """严格匹配不能误伤真实抖音域名。"""
    monkeypatch.setattr(
        summarizer,
        "_parse_douyin_video_info",
        lambda url: {"desc": "视频文案", "video_id": "1"},
    )

    def fail_generic(self, url):
        raise AssertionError("真实抖音链接不应走 yt-dlp 通用流程")

    monkeypatch.setattr(summarizer.SubtitleExtractor, "_get_video_info", fail_generic)

    result = summarizer.SubtitleExtractor().extract("https://v.douyin.com/iRNBho6u/")

    assert result["has_subtitle"] is True
    assert result["full_text"] == "视频文案"


def test_extract_does_not_use_other_video_subtitles_for_spoofed_bilibili_host(monkeypatch):
    """非 B 站域名即使带 BV 号，也不能去 B 站接口取字幕。"""
    calls = {"bilibili": 0, "generic": 0}

    def fake_bilibili(self, url):
        calls["bilibili"] += 1
        return {"has_subtitle": False, "language": "", "subtitle_type": "none",
                "segments": [], "full_text": ""}

    def fake_generic(self, url):
        calls["generic"] += 1
        return {}

    monkeypatch.setattr(summarizer.SubtitleExtractor, "_extract_bilibili", fake_bilibili)
    monkeypatch.setattr(summarizer.SubtitleExtractor, "_get_video_info", fake_generic)

    summarizer.SubtitleExtractor().extract("https://notbilibili.com/video/BV1xx411c7mD")

    assert calls["bilibili"] == 0
    assert calls["generic"] == 1


# ---------- 配额清理并发容错 ----------

def test_enforce_quota_ignores_files_vanished_after_listdir(monkeypatch, tmp_path):
    """listdir 之后文件被并发 rename/删除时，不能抛 FileNotFoundError 拖垮下载请求。"""
    d = tmp_path / "downloads"
    d.mkdir()
    target = d / "big.mp4"
    target.write_bytes(b"x" * 100)
    abs_dir = os.path.abspath(str(d))

    real_listdir = os.listdir

    def fake_listdir(path):
        names = real_listdir(path)
        if os.path.abspath(str(path)) == abs_dir:
            names = names + ["ghost.mp4"]  # 模拟 listdir 之后被 rename 走的名字
        return names

    monkeypatch.setattr(downloader.os, "listdir", fake_listdir)

    downloader._enforce_quota(str(d), limit=10)  # 修复前：这里抛 FileNotFoundError

    assert not target.exists(), "超配额时应删除已完成文件"


def test_enforce_quota_prefers_deleting_finished_files(monkeypatch, tmp_path):
    """配额清理保持既有语义：先删已完成文件，.part 最后删。"""
    d = tmp_path / "downloads"
    d.mkdir()
    finished = d / "old.mp4"
    finished.write_bytes(b"x" * 100)
    part = d / "new.mp4.part"
    part.write_bytes(b"x" * 100)
    # 让 .part 的 mtime 更旧，验证排序优先看「是否为 .part」而非单纯 mtime
    os.utime(str(part), (1_000_000, 1_000_000))

    downloader._enforce_quota(str(d), limit=100)

    assert not finished.exists()
    assert part.exists()
