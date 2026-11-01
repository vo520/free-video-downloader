"""回归：演示账号 VIP 体验期限（防止被改回长期 VIP 导致付费墙失效）。"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_demo_vip_duration_is_short_lived():
    """demo 账号的 VIP 只能是短期体验额度。

    前端在未登录时会用固定 demo 账号静默登录（api/auth.js#ensureDefaultUser），
    所有访客都落在同一个 demo 账号上。若 demo 账号带长期 VIP，
    免费 3 次/日的解析配额与付费墙对全部访客失效，VIP 付费只剩名义门槛。
    """
    import api_auth

    assert api_auth.DEMO_VIP_DURATION <= timedelta(days=1), (
        f"demo VIP 期限不应超过 1 天，当前为 {api_auth.DEMO_VIP_DURATION}"
    )


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """把 users/history 表指向临时库，避免污染真实数据。"""
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    return database


def test_demo_vip_expiry_is_within_one_day(temp_db):
    """_ensure_demo_vip 写入的到期时间必须落在 1 天内。"""
    import api_auth

    database = temp_db
    database.create_user(api_auth.DEMO_EMAIL, "x")

    api_auth._ensure_demo_vip(api_auth.DEMO_EMAIL)

    user = database.get_user_by_email(api_auth.DEMO_EMAIL)
    assert user is not None
    assert user["is_vip"] == 1
    assert user["vip_expire_at"], "demo 账号必须有 vip_expire_at"

    expire = datetime.fromisoformat(user["vip_expire_at"].replace("Z", "+00:00"))
    if expire.tzinfo is None:
        expire = expire.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    assert expire > now, "demo VIP 到期时间必须晚于当前时间"
    assert expire <= now + timedelta(days=1, minutes=1), (
        f"demo VIP 到期时间超出 1 天：{user['vip_expire_at']}"
    )


def test_non_demo_user_is_not_promoted(temp_db):
    """普通用户不得因为 _ensure_demo_vip 被提升为 VIP。"""
    import api_auth

    database = temp_db
    database.create_user("normal@example.com", "x")

    api_auth._ensure_demo_vip("normal@example.com")

    user = database.get_user_by_email("normal@example.com")
    assert user["is_vip"] == 0


# ===== 缓存规则 / 解析日志：此前两套能力完全没有被激活 =====


@pytest.fixture()
def cache_db(tmp_path, monkeypatch):
    """指向临时库的 VideoCacheDB 实例。"""
    import video_cache_db as vcdb

    monkeypatch.setattr(vcdb, "VIDEO_CACHE_DB_PATH", str(tmp_path / "video_cache.db"))
    return vcdb.VideoCacheDB()


def test_default_cache_rules_are_seeded(cache_db):
    """全新部署时 cache_rules 表必须被写入内置规则。

    规则表此前恒空 → get_cache_ttl 遍历不到任何规则，永远回退到硬编码 86400，
    "按平台/时长差异化 TTL" 的机制等于不存在。
    """
    rules = cache_db.get_cache_rules()
    names = {r["rule_name"] for r in rules}
    assert {"default", "short_video", "long_video"} <= names


def test_seeding_does_not_override_existing_rules(cache_db):
    """表非空时不再播种，用户改过的规则不会在重启后被默认值覆盖。"""
    # 用户把内置 default 规则改成自定义 TTL
    cache_db.save_cache_rule(
        {
            "rule_name": "default",
            "rule_type": "ttl",
            "ttl_seconds": 60,
            "priority": 99,
            "is_active": True,
        }
    )

    # 重新初始化（等价于进程重启）
    cache_db._init_db()

    rules = {r["rule_name"]: r for r in cache_db.get_cache_rules()}
    assert rules["default"]["ttl_seconds"] == 60
    assert rules["default"]["priority"] == 99


def test_cache_ttl_actually_uses_rules(cache_db):
    """TTL 必须随规则命中结果变化，而不是恒定 24 小时。"""
    from video_cache_manager import VideoCacheManager

    manager = VideoCacheManager()
    manager.db = cache_db

    # 短视频（≤5 分钟）命中 short_video 规则 → 6 小时
    assert manager.get_cache_ttl("https://x.com/v", "youtube", "720p", 120) == 21600
    # 长视频（≥30 分钟）命中 long_video 规则 → 3 天
    assert manager.get_cache_ttl("https://x.com/v", "youtube", "720p", 3600) == 259200
    # 落回 default → 24 小时
    assert manager.get_cache_ttl("https://x.com/v", "youtube", "720p", 900) == 86400


def test_parse_log_is_recorded(tmp_path, monkeypatch):
    """_record_parse_log 必须真的写入 parse_logs（此前无任何写入方）。"""
    import video_cache_db as vcdb
    import main

    monkeypatch.setattr(vcdb, "VIDEO_CACHE_DB_PATH", str(tmp_path / "video_cache.db"))
    db = vcdb.VideoCacheDB()
    monkeypatch.setattr(vcdb, "video_cache_db", db)

    main._record_parse_log(
        "https://example.com/v", "youtube", True, 1234, "解析成功: demo", ""
    )

    logs = db.get_parse_logs(limit=10)
    assert len(logs) == 1
    assert logs[0]["url"] == "https://example.com/v"
    assert logs[0]["success"] == 1
    assert logs[0]["duration_ms"] == 1234
    assert "解析成功" in logs[0]["message"]


def test_parse_log_failure_does_not_break_parse(tmp_path, monkeypatch):
    """日志写入失败必须被吞掉，不能影响解析主流程。"""
    import main

    class _BrokenDB:
        def save_parse_log(self, *_args, **_kwargs):
            raise RuntimeError("db down")

    import video_cache_db as vcdb

    monkeypatch.setattr(vcdb, "video_cache_db", _BrokenDB())

    # 不抛异常即通过
    main._record_parse_log("https://example.com/v", None, False, 10, "", "boom")
