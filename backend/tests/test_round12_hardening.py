"""回归：缓存生命周期报告的年龄分布必须覆盖全表，且不能丢存量无时区记录。

根因：原实现用 get_videos(limit=100)（按 created_at DESC 取最新 100 条）统计年龄桶，
总记录超过 100 时更老的记录进不了任何桶，gt_30d 被系统性低估，
「建议缩短长龄缓存 TTL」的推荐永远不触发；另外 created_at 缺时区的存量记录
做 now - created_at 会抛 TypeError 被跳过，同样不计入任何桶。
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import video_cache_db
from video_cache_db import VideoCacheDB

URL_PREFIX = "https://age.test/v"


@pytest.fixture()
def db(tmp_path):
    video_cache_db.VIDEO_CACHE_DB_PATH = str(tmp_path / "vc.db")
    return VideoCacheDB()


def _manager(db):
    import video_cache_manager

    mgr = video_cache_manager.VideoCacheManager.__new__(video_cache_manager.VideoCacheManager)
    mgr.db = db
    mgr._hot_cache_threshold = 100
    return mgr


def _save(db, i):
    url = f"{URL_PREFIX}{i}"
    db.save_video({
        "url": url,
        "video_info": {"platform": "youtube", "video_id": str(i), "title": "t"},
        "metadata": {},
        "success": True,
    })
    return url


def _set_created_at(db, url, value):
    with db._conn() as conn:
        conn.execute("UPDATE video_cache SET created_at=? WHERE video_url=?", (value, url))


def test_age_distribution_covers_rows_beyond_recent_100(db):
    """120 条缓存中最早的 20 条已 40 天，gt_30d 必须统计到这 20 条。"""
    total = 120
    old = 20
    urls = [_save(db, i) for i in range(total)]

    old_ts = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    for url in urls[:old]:
        _set_created_at(db, url, old_ts)

    by_age = _manager(db).get_lifecycle_report()["by_age"]
    assert by_age["gt_30d"] == old, f"长龄记录被截断：{by_age}"
    # 所有记录都必须落入某个桶，不能有遗漏
    assert sum(by_age.values()) == total, by_age


def test_age_distribution_counts_naive_created_at(db):
    """存量无时区 created_at 不能因 TypeError 被静默丢弃。"""
    url = _save(db, 0)
    _set_created_at(db, url, "2020-01-01T00:00:00")

    by_age = _manager(db).get_lifecycle_report()["by_age"]
    assert by_age["gt_30d"] == 1, by_age
    assert sum(by_age.values()) == 1
