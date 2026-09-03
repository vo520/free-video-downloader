import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database
import pytest

# 用 autouse fixture 在“运行时”设置独立临时库并建表，避免多个测试文件在导入期
# 争抢共享的 database.DB_PATH 全局变量（导致 init_db 与 add_history 落在不同库）。
@pytest.fixture(autouse=True)
def isolated_db():
    tmp = tempfile.mkdtemp()
    database.DB_PATH = os.path.join(tmp, "dedup.db")
    database.init_db()
    yield


def _make_user(uid: int):
    # history.user_id 有外键约束，必须先存在对应 users 行（与生产一致：user_id 来自真实登录用户）。
    with database.get_db() as conn:
        conn.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            (uid, f"u{uid}@test.com", "x"),
        )


def test_dedup_same_url_same_type_updates():
    uid = 991001
    _make_user(uid)
    database.add_history(uid, "parse", "https://x/v1", title="旧标题")
    # 同 (user_id, type, video_url) 再次记录，应 UPDATE 而非 INSERT
    database.add_history(uid, "parse", "https://x/v1", title="新标题", platform="douyin")
    rows, total = database.get_history(uid, htype="parse")
    assert total == 1, f"去重失败：期望 1 行，实际 {total}"
    assert rows[0]["title"] == "新标题"
    assert rows[0]["platform"] == "douyin"


def test_different_url_stays_separate():
    uid = 991002
    _make_user(uid)
    database.add_history(uid, "parse", "https://x/a")
    database.add_history(uid, "parse", "https://x/b")
    rows, total = database.get_history(uid, htype="parse")
    assert total == 2


def test_different_type_same_url_separate():
    uid = 991003
    _make_user(uid)
    database.add_history(uid, "parse", "https://x/same")
    database.add_history(uid, "download", "https://x/same")
    rows, total = database.get_history(uid)
    assert total == 2


def test_empty_url_skipped():
    uid = 991004
    _make_user(uid)
    assert database.add_history(uid, "parse", "") is None
    rows, total = database.get_history(uid, htype="parse")
    assert total == 0


def test_anonymous_skipped():
    assert database.add_history(None, "parse", "https://x/z") is None
    rows, total = database.get_history(123456, htype="parse")
    assert total == 0


def test_url_normalization_dedupes_variants():
    # http/www/#fragment 等形态差异应被归一为同一视频，去重生效
    uid = 991005
    _make_user(uid)
    database.add_history(uid, "parse", "http://www.example.com/v?x=1#frag")
    database.add_history(uid, "parse", "https://example.com/v?x=1")
    rows, total = database.get_history(uid, htype="parse")
    assert total == 1, f"URL 归一化去重失败：期望 1 行，实际 {total}"
