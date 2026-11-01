"""回归：存量缓存 URL 归一化迁移、清空历史返回实际条数。"""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import video_cache_db
from video_cache_db import VideoCacheDB


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "vc.db")


def _legacy_db(path):
    """造一个"老口径"的缓存库：video_url 保留 www./http/fragment。"""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS video_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_url TEXT UNIQUE NOT NULL,
            url_hash TEXT NOT NULL,
            platform TEXT,
            video_id TEXT,
            title TEXT,
            description TEXT,
            uploader TEXT,
            thumbnail_url TEXT,
            duration REAL DEFAULT 0,
            width INTEGER DEFAULT 0,
            height INTEGER DEFAULT 0,
            fps REAL DEFAULT 0,
            codec TEXT,
            bitrate INTEGER DEFAULT 0,
            file_size INTEGER DEFAULT 0,
            format TEXT,
            quality TEXT,
            parse_timestamp TEXT,
            parse_success INTEGER,
            parse_error TEXT,
            cache_status TEXT DEFAULT 'active',
            cache_expires_at TEXT,
            cache_hit_count INTEGER DEFAULT 0,
            is_hot INTEGER DEFAULT 0,
            direct_url TEXT,
            download_url TEXT,
            available_formats TEXT,
            last_access_at TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def test_migration_rewrites_legacy_urls(db_path):
    """老库里的 URL 必须被重写成新口径，否则新代码按新口径查不到。"""
    _legacy_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO video_cache (video_url, url_hash, cache_hit_count) VALUES (?, ?, ?)",
        ("http://www.Example.com/v#frag", "oldhash", 3),
    )
    conn.commit()
    conn.close()

    db = VideoCacheDB(db_path)  # 构造时执行迁移

    row = db.get_video("https://example.com/v")
    assert row is not None, "迁移后应能用新口径查到"
    assert row["video_url"] == "https://example.com/v"
    assert row["url_hash"] != "oldhash"
    # 命中数必须保留（迁移不能丢业务数据）
    assert row["cache_hit_count"] == 3


def test_migration_merges_duplicates(db_path):
    """两条归一化后相同的记录应合并成一条，命中数累加、热门标记保留。"""
    _legacy_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO video_cache (video_url, url_hash, cache_hit_count, is_hot) VALUES (?, ?, ?, ?)",
        ("http://www.Example.com/v", "h1", 2, 0),
    )
    conn.execute(
        "INSERT INTO video_cache (video_url, url_hash, cache_hit_count, is_hot) VALUES (?, ?, ?, ?)",
        ("https://example.com/v", "h2", 5, 1),
    )
    conn.commit()
    conn.close()

    db = VideoCacheDB(db_path)

    with db._conn() as c:
        total = c.execute("SELECT COUNT(*) FROM video_cache").fetchone()[0]
    assert total == 1, "归一化后重复的记录应合并为一条"

    row = db.get_video("https://example.com/v")
    assert row["cache_hit_count"] == 7, "命中数应累加"
    assert row["is_hot"] == 1, "热门标记应保留"


def test_migration_is_idempotent(db_path):
    """迁移可重复执行，不应破坏数据。"""
    _legacy_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO video_cache (video_url, url_hash) VALUES (?, ?)",
        ("http://www.Example.com/v", "h1"),
    )
    conn.commit()
    conn.close()

    VideoCacheDB(db_path)
    VideoCacheDB(db_path)  # 再跑一次

    db = VideoCacheDB(db_path)
    row = db.get_video("https://example.com/v")
    assert row is not None
    assert row["video_url"] == "https://example.com/v"


def test_clear_history_returns_deleted_count(tmp_path, monkeypatch):
    """清空历史要返回实际删除条数（跨全部类型），前端提示才不会对不上。"""
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    user = database.create_user("clear@example.com", "x")

    database.add_history(user["id"], "parse", video_url="https://a.test/1", title="p")
    database.add_history(user["id"], "download", video_url="https://a.test/2", title="d")
    database.add_history(user["id"], "summary", video_url="https://a.test/3", title="s")

    assert database.clear_history(user["id"]) == 3
    # 再清一次应为 0
    assert database.clear_history(user["id"]) == 0
