"""回归：缓存统计的「过期」口径必须与 cleanup_expired 一致。

根因：get_stats 只按 cache_status='expired' 统计过期数，而系统从不会把到期的行
写成该状态（cleanup_expired 按 cache_expires_at 直接 DELETE）。结果：
- 「已过期但尚未被清理」的行恒被算作 active，过期数恒为 0；
- monitor/health 里「过期缓存比例过高」的扣分分支永远不触发；
- lifecycle 建议里「建议立即清理过期缓存」同样成为死代码。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import video_cache_db
from video_cache_db import VideoCacheDB

URL = "https://stats.test/v"


@pytest.fixture()
def db(tmp_path):
    video_cache_db.VIDEO_CACHE_DB_PATH = str(tmp_path / "vc.db")
    return VideoCacheDB()


def _save(db, url=URL):
    db.save_video({
        "url": url,
        "video_info": {"platform": "youtube", "video_id": "a", "title": "t"},
        "metadata": {},
        "success": True,
    })


def test_stats_counts_time_expired_as_expired(db):
    """到期时间已过、但尚未被 cleanup 删除的行，必须计入 expired_cache。"""
    _save(db)
    db.update_cache_status(URL, "active", "2000-01-01T00:00:00+00:00")

    stats = db.get_stats()
    assert stats["expired_cache"] == 1, "已到期行未被计入过期统计"
    assert stats["active_cache"] == 0, "已到期行仍被计入有效缓存"
    assert stats["total_videos"] == 1


def test_stats_counts_status_expired(db):
    """显式标记为 expired 的行（到期时间仍在未来）同样计入过期数。"""
    _save(db)
    db.update_cache_status(URL, "expired")

    stats = db.get_stats()
    assert stats["expired_cache"] == 1
    assert stats["active_cache"] == 0


def test_stats_matches_cleanup_expired(db):
    """统计口径与清理口径一致：统计为过期的行，cleanup 必须能删掉。"""
    _save(db)
    db.update_cache_status(URL, "active", "2000-01-01T00:00:00+00:00")

    assert db.get_stats()["expired_cache"] == 1
    assert db.cleanup_expired() == 1
    stats = db.get_stats()
    assert stats["expired_cache"] == 0
    assert stats["total_videos"] == 0
