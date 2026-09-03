import sys
import os
import tempfile
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database
import pytest


@pytest.fixture(autouse=True)
def isolated_db():
    tmp = tempfile.mkdtemp()
    database.DB_PATH = os.path.join(tmp, "upsert_index.db")
    database.init_db()
    yield


def _make_user(uid: int):
    with database.get_db() as conn:
        conn.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            (uid, f"u{uid}@t.com", "x"),
        )


def test_unique_index_blocks_duplicate_direct_insert():
    # 绕过 add_history 直接插入冲突行，验证唯一索引物理存在并能拦住重复
    # （这是并发竞态的最终防线：即使两个事务同时判定「不存在」，唯一索引也会让后者失败而非产生重复）。
    uid = 992001
    _make_user(uid)
    with database.get_db() as conn:
        conn.execute(
            "INSERT INTO history (user_id, type, video_url) VALUES (?, ?, ?)",
            (uid, "parse", "https://x/v"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO history (user_id, type, video_url) VALUES (?, ?, ?)",
                (uid, "parse", "https://x/v"),
            )


def test_migration_normalizes_and_dedups_legacy_rows():
    # 模拟早期落库的非归一化 URL（http/www/#frag），init_db 迁移应归一并去重为 1 行。
    uid = 992002
    _make_user(uid)
    with database.get_db() as conn:
        conn.execute(
            "INSERT INTO history (user_id, type, video_url, title) VALUES (?, ?, ?, ?)",
            (uid, "parse", "http://www.example.com/v#frag", "A"),
        )
        conn.execute(
            "INSERT INTO history (user_id, type, video_url, title) VALUES (?, ?, ?, ?)",
            (uid, "parse", "https://example.com/v", "B"),
        )
    # 重跑迁移（init_db 幂等），模拟服务重启后存量数据被加固。
    database.init_db()
    rows, total = database.get_history(uid, htype="parse")
    assert total == 1, f"存量非归一化 URL 未去重：期望 1 行，实际 {total}"
    assert rows[0]["video_url"] == "https://example.com/v", "保留行 video_url 未归一化"


def test_migration_idempotent_on_clean_db():
    # init_db 连续重跑不应丢数据或报错（幂等）。
    uid = 992003
    _make_user(uid)
    database.add_history(uid, "parse", "https://y/v", title="Y")
    database.init_db()  # 第二次
    database.init_db()  # 第三次
    rows, total = database.get_history(uid, htype="parse")
    assert total == 1
    assert rows[0]["title"] == "Y"
