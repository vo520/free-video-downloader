"""回归：抖音并发下载临时文件冲突、下载兜底误取半截文件、B 站短链与无字幕回退。

缺陷一（douyin）：`_download_file` 的临时文件名固定为 `<filename>.part`，同名视频并发
下载时两个请求共用同一路径：后开始的 "wb" 会截断前者已写入的内容，各自 fd 的写偏移还会
在文件里留下空洞；任一请求失败时的 unlink 会删掉另一个请求正在写的文件，最终可能把半截
文件 rename 成正式文件返回给用户。

缺陷二（downloader）：`download_video` 兜底定位落盘文件时用 `_vid in f`，会命中 `.part`
半截文件，或 "12345" 命中 "912345" 这类别的视频，且取 listdir 顺序的第一个导致结果不稳定。

缺陷三（summarizer）：B 站无字幕时旧代码继续落到必然 412 的通用 yt-dlp 路径；`b23.tv`
短链里没有 BV 号，`_parse_bvid` 直接取不到，短链永远无法总结。
"""
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import douyin
import downloader
import summarizer


# ---------- 缺陷一：并发同名下载临时文件唯一 ----------

class _FakeResponse:
    def __init__(self, chunks):
        self._chunks = chunks
        self.is_redirect = False
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=65536):
        for c in self._chunks:
            yield c


class _FakeSession:
    def __init__(self, routes):
        self._routes = routes

    def get(self, url, **kwargs):
        return _FakeResponse(self._routes[url])


def _make_douyin_parser(monkeypatch, tmp_path, routes):
    parser = douyin.DouyinParser.__new__(douyin.DouyinParser)
    parser.download_dir = tmp_path
    parser.session = _FakeSession(routes)
    parser.timeout = (10, 30)
    # 单次尝试：失败立即抛出，避免重试掩盖不同临时文件带来的差异
    parser.max_retries = 1
    monkeypatch.setattr(douyin, "_is_public_http_url", lambda url: True)
    return parser


def test_concurrent_same_name_downloads_do_not_share_temp_file(monkeypatch, tmp_path):
    """同名视频并发下载必须各自写独立临时文件，否则最终文件会被写坏。"""
    filepath = tmp_path / "同名视频_1.mp4"
    first_chunk_written = threading.Event()
    b_finished = threading.Event()

    def a_chunks():
        yield b"A" * 8
        first_chunk_written.set()
        # 等 B 完整下载并把结果 rename 成正式文件后，A 继续写剩余内容
        assert b_finished.wait(timeout=10)
        yield b"A" * 8

    def b_chunks():
        yield b"B" * 8

    parser = _make_douyin_parser(monkeypatch, tmp_path, {
        "http://example.com/a": a_chunks(),
        "http://example.com/b": b_chunks(),
    })

    errors = []

    def download_a():
        try:
            parser._download_file("http://example.com/a", filepath)
        except Exception as e:  # 修复前：A 的临时文件已被 B rename 走，replace 抛错
            errors.append(e)

    def download_b():
        assert first_chunk_written.wait(timeout=10)
        try:
            parser._download_file("http://example.com/b", filepath)
        except Exception as e:
            errors.append(e)
        finally:
            b_finished.set()

    ta = threading.Thread(target=download_a)
    tb = threading.Thread(target=download_b)
    ta.start()
    tb.start()
    ta.join(timeout=15)
    tb.join(timeout=15)

    assert errors == []
    # 修复前两请求共用 ".part"：B 截断后写入 B，A 在自己的旧偏移继续写，
    # 最终内容会是 B"A" 混合；修复后以最后完成的 A 为准，内容完整且连续。
    assert filepath.read_bytes() == b"A" * 16
    leftovers = [p for p in tmp_path.iterdir() if p.name.endswith(".part")]
    assert leftovers == []


# ---------- 缺陷二：兜底只接受已完成文件，且精确 id 优先 ----------

class _FakeYDL:
    def __init__(self, info, prepared):
        self._info = info
        self._prepared = prepared

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        return self._info

    def prepare_filename(self, info):
        return self._prepared


def _make_downloader(monkeypatch, tmp_path):
    dl = downloader.VideoDownloader.__new__(downloader.VideoDownloader)
    dl.DOWNLOAD_DIR = str(tmp_path)
    dl.ffmpeg_path = None
    dl.has_ffmpeg = False
    monkeypatch.setattr(dl, "ensure_disk_quota", lambda: None)
    return dl


def _patch_ydl(monkeypatch, info, prepared):
    monkeypatch.setattr(
        downloader.yt_dlp,
        "YoutubeDL",
        lambda opts: _FakeYDL(info, prepared),
    )


def test_download_fallback_ignores_part_file(monkeypatch, tmp_path):
    """目录里只有 .part 半截文件时，不能把它当作下载结果返回。"""
    (tmp_path / "t [12345].mp4.part").write_bytes(b"half")
    _patch_ydl(monkeypatch, {"id": "12345"}, str(tmp_path / "missing.mp4"))
    dl = _make_downloader(monkeypatch, tmp_path)

    with pytest.raises(FileNotFoundError):
        dl.download_video("https://example.com/v", "best")


def test_download_fallback_prefers_exact_id_match(monkeypatch, tmp_path):
    """id 子串必须精确到 "[id].ext"，不能返回 "912345" 这类别的视频。"""
    (tmp_path / "teaser [912345].mp4").write_bytes(b"other")
    (tmp_path / "t [12345].mp4").write_bytes(b"mine")
    _patch_ydl(monkeypatch, {"id": "12345"}, str(tmp_path / "missing.mp4"))
    dl = _make_downloader(monkeypatch, tmp_path)

    # 打乱 listdir 顺序，确保结果不依赖目录遍历顺序
    monkeypatch.setattr(
        downloader.os,
        "listdir",
        lambda path: ["teaser [912345].mp4", "t [12345].mp4"],
    )

    result = dl.download_video("https://example.com/v", "best")

    assert os.path.basename(result["filepath"]) == "t [12345].mp4"


# ---------- 缺陷三：B 站短链解析 + 无字幕不回退 ----------

class _FakeHttpxResponse:
    def __init__(self, payload, url=""):
        self._payload = payload
        self.url = url

    def json(self):
        return self._payload


def test_b23_short_link_resolves_bvid_and_extracts_subtitle(monkeypatch):
    """b23.tv 短链没有 BV 号，必须跟随跳转拿到真实地址后才能取字幕。"""
    real_url = "https://www.bilibili.com/video/BV1xx411c7mD"
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if url == "https://b23.tv/abcdefg":
            return _FakeHttpxResponse({}, url=real_url)
        if "x/web-interface/view" in url:
            return _FakeHttpxResponse({"data": {"cid": 1, "aid": 2}})
        if "x/v2/dm/view" in url:
            return _FakeHttpxResponse({"data": {"subtitle": {"subtitles": [
                {"lan": "zh", "subtitle_url": "//example.com/sub.json"},
            ]}}})
        if url.endswith("/sub.json"):
            return _FakeHttpxResponse({"body": [{"content": "你好", "from": 0, "to": 1}]})
        raise AssertionError(f"未预期的请求: {url}")

    monkeypatch.setattr(summarizer.httpx, "get", fake_get)

    def fail_generic(self, url):
        raise AssertionError("b23.tv 短链不应落到必然 412 的通用 yt-dlp 路径")

    monkeypatch.setattr(summarizer.SubtitleExtractor, "_get_video_info", fail_generic)

    result = summarizer.SubtitleExtractor().extract("https://b23.tv/abcdefg")

    assert result["has_subtitle"] is True
    assert result["full_text"] == "你好"
    assert calls[0] == "https://b23.tv/abcdefg"


def test_bilibili_without_subtitle_does_not_fall_back_to_generic(monkeypatch):
    """B 站无字幕时必须直接返回无字幕，不能回落到固定 412 的通用路径。"""
    empty = {
        "has_subtitle": False, "language": "", "subtitle_type": "none",
        "segments": [], "full_text": "",
    }
    monkeypatch.setattr(
        summarizer.SubtitleExtractor, "_extract_bilibili", lambda self, url: empty
    )

    def fail_generic(self, url):
        raise AssertionError("B 站不应回落到通用 yt-dlp 路径")

    monkeypatch.setattr(summarizer.SubtitleExtractor, "_get_video_info", fail_generic)

    result = summarizer.SubtitleExtractor().extract(
        "https://www.bilibili.com/video/BV1xx411c7mD"
    )

    assert result["has_subtitle"] is False
    assert result["full_text"] == ""
