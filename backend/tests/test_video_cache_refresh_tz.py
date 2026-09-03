"""回归：refresh_cache 必须写入带 UTC 时区的 expires_at，否则与 save_video 写入的
有 tz 字符串比较时被立即判过期（字符串字典序："2026-08-19T20:00:00" < "2026-08-19T12:00:00+00:00"）。

测试通过在 VideoCacheManager 构造后注入测试用 db（避免单例在不同 db_path 上的状态串扰），
覆盖三个核心断言：save_video 写入带 tz、refresh_cache 后 expires_at 带 tz 且不被
cleanup_expired 误删、与 save_video 一致可比较。
"""
import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import video_cache_db
from video_cache_db import VideoCacheDB
from video_cache_manager import VideoCacheManager


_TMP_DB = tempfile.mkstemp(suffix=".db")[1]


def _cleanup_tmp():
    for suffix in ("", "-wal", "-shm"):
        p = _TMP_DB + suffix
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


import atexit
atexit.register(_cleanup_tmp)


def _sample(url):
    return {
        "url": url,
        "video_info": {
            "platform": "youtube",
            "video_id": "abc",
            "title": "Test",
            "uploader": "u",
            "thumbnail": "https://x/y.jpg",
        },
        "metadata": {"duration": 60, "width": 1920, "height": 1080},
        "success": True,
    }


def _build_db_with_test_path():
    """构造一个使用测试 db_path 的 VideoCacheDB 实例。"""
    video_cache_db.VIDEO_CACHE_DB_PATH = _TMP_DB
    return VideoCacheDB()


def test_save_writes_tz_aware_expires_at():
    """save_video 必须写入带 UTC 时区的 expires_at，作为契约基线。"""
    db = _build_db_with_test_path()
    url = "https://example.com/a"
    db.save_video(_sample(url))
    row = db.get_video(url)
    assert row is not None
    expires = row["cache_expires_at"]
    assert expires is not None
    # 必须含时区标识（"+00:00" 或 "Z"），否则后续字符串比较会被立即判过期
    assert "+" in expires or expires.endswith("Z"), f"save_video 未写入 tz: {expires!r}"


def test_refresh_cache_preserves_future_expiry():
    """refresh_cache 后 expires_at 必须含 tz，且大于当前 UTC，cleanup_expired 不应删。"""
    db = _build_db_with_test_path()
    url = "https://example.com/b"
    db.save_video(_sample(url))

    # 注入测试用 db 到 manager（避免模块级单例与测试 db_path 状态串扰）
    manager = VideoCacheManager()
    manager.db = db

    ok = manager.refresh_cache(url, new_ttl=86400)
    assert ok is True, "refresh_cache 应返回 True"

    row = db.get_video(url)
    expires = row["cache_expires_at"]
    # 必须含 tz（修复前的 BUG：无 tz 字符串被立即判过期）
    assert "+" in expires or expires.endswith("Z"), f"refresh_cache 未写入 tz: {expires!r}"

    # cleanup_expired 不应把它清掉（时间仍在未来）
    deleted = db.cleanup_expired()
    assert deleted == 0, "refresh_cache 后不应被 cleanup_expired 误删"
    assert db.get_video(url) is not None


def test_refresh_cache_uses_utc_consistent_with_save():
    """refresh_cache 写入的 expires_at 与 save_video 写入的字符串按字典序一致可比较。"""
    db = _build_db_with_test_path()
    url = "https://example.com/c"
    db.save_video(_sample(url))
    saved = db.get_video(url)["cache_expires_at"]

    manager = VideoCacheManager()
    manager.db = db
    manager.refresh_cache(url, new_ttl=86400)
    refreshed = db.get_video(url)["cache_expires_at"]

    parse = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
    assert parse(refreshed) > datetime.now(timezone.utc), (
        f"refresh_cache 后 expires_at 仍在过去: {refreshed}"
    )
    # 与 save 写入的同形态（都有 tz），保证字符串可比较
    assert ("+" in saved or saved.endswith("Z")) and (
        "+" in refreshed or refreshed.endswith("Z")
    )