"""回归：SSRF 判定口径统一 / 缓存搜索通配符转义 / 抖音时长毫秒边界（第 9 轮自主排查）。

本轮修复的三个真实缺陷：

1. `main._validate_public_url`（解析 / 下载 / 直链 / AI 总结共用的入口校验）
   只依赖标准库的 `is_private / is_unspecified / is_loopback / is_link_local /
   is_reserved / is_multicast` 判定，而同文件的 `_BLOCKED_NETS` 黑名单里明确包含
   `100.64.0.0/10`（共享地址段）—— 两者口径不一致。
   关键事实：Python 3.13 官方文档写明该段的 `is_private` 与 `is_global` **均为
   False**，所以标准库分类根本拦不住它；而阿里云元数据服务 100.100.100.200 正落在
   该段内 → 任意用户可用 /api/parse 探测云元数据。
   修复：解析/下载/直链入口复用与缩略图代理同一份 `_BLOCKED_NETS`。

2. `video_cache_db._build_filters` 的 search 未转义 LIKE 通配符：搜 "%" 会匹配
   全部记录、搜 "_" 会变成单字符通配；而同项目的 `database.get_history` 早已做了
   转义（ESCAPE '\'），同一产品内两处搜索行为不一致。

3. `douyin._build_result` 的时长换算用 `duration > 1000` 判毫秒，恰好漏掉 1000
   本身：1 秒的短视频（抖音上非常常见）会落到 else 分支被当成 1000 秒，
   时长显示成 16:40；同时该值会写入 video_cache.duration 并参与缓存规则的
   时长匹配，导致短视频命中错误的 TTL 档位。
"""
import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import video_cache_db  # noqa: E402
from video_cache_db import VideoCacheDB  # noqa: E402


def _fake_getaddrinfo(addr):
    return lambda *a, **k: [(None, None, None, None, (addr, 0))]


# ---------- 缺陷 1：SSRF 判定口径不一致 ----------


@pytest.mark.parametrize(
    "addr",
    [
        "100.64.0.1",       # 共享地址段起始
        "100.100.100.200",  # 阿里云元数据服务
        "100.127.255.254",  # 共享地址段末尾
    ],
)
def test_validate_public_url_rejects_shared_address_space(addr):
    """共享地址段（100.64.0.0/10）必须被解析/下载/直链入口拒绝。

    标准库的 is_private / is_global 对该段均为 False，只依赖它们会整段放行。
    """
    import main
    from fastapi import HTTPException

    with mock.patch.object(main.socket, "getaddrinfo", _fake_getaddrinfo(addr)):
        with pytest.raises(HTTPException) as exc:
            main._validate_public_url("https://evil.example.com/x.mp4")
    assert exc.value.status_code == 400


def test_validate_public_url_rejects_shared_address_space_via_ipv4_mapped():
    """IPv4-mapped IPv6 形式（::ffff:100.100.100.200）同样必须被拒绝。

    _validate_public_url 会先把 IPv4-mapped IPv6 还原成内嵌 IPv4 再判定，
    因此该写法不能绕过共享地址段黑名单。
    """
    import main
    from fastapi import HTTPException

    with mock.patch.object(
        main.socket, "getaddrinfo", _fake_getaddrinfo("::ffff:100.100.100.200")
    ):
        with pytest.raises(HTTPException) as exc:
            main._validate_public_url("https://evil.example.com/x.mp4")
    assert exc.value.status_code == 400


def test_validate_public_url_still_allows_public_address():
    """正常公网地址不得被误伤（修复不能把解析入口整体堵死）。"""
    import main

    with mock.patch.object(main.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34")):
        assert (
            main._validate_public_url("https://www.douyin.com/video/7001234")
            == "https://www.douyin.com/video/7001234"
        )


def test_validate_public_url_matches_thumbnail_proxy_decision():
    """解析入口与缩略图代理对同一地址必须给出相同结论（口径统一）。

    缩略图代理此前已用 _BLOCKED_NETS 拦截共享地址段；解析/下载/直链入口必须一致，
    否则同一个恶意地址「能代理就不能解析」，防护形同虚设。
    """
    import main

    for addr in ("100.100.100.200", "93.184.216.34"):
        with mock.patch.object(main.socket, "getaddrinfo", _fake_getaddrinfo(addr)):
            thumbnail_ok = main._is_safe_thumbnail_url("https://img.example.com/a.jpg")
            try:
                main._validate_public_url("https://v.example.com/a.mp4")
                validate_ok = True
            except Exception:
                validate_ok = False
        assert thumbnail_ok == validate_ok, f"{addr} 两处判定不一致"


# ---------- 缺陷 2：缓存搜索未转义 LIKE 通配符 ----------


@pytest.fixture()
def cache_db(tmp_path):
    video_cache_db.VIDEO_CACHE_DB_PATH = str(tmp_path / "vc.db")
    return VideoCacheDB()


def _seed_cache(db):
    db.save_video({
        "url": "https://www.youtube.com/watch?v=abc",
        "video_info": {"platform": "youtube", "video_id": "abc", "title": "正常标题"},
        "metadata": {},
        "success": True,
    })
    db.save_video({
        "url": "https://www.bilibili.com/video/BV1xx",
        "video_info": {"platform": "bilibili", "video_id": "BV1xx", "title": "50% 优惠"},
        "metadata": {},
        "success": True,
    })


def test_cache_search_percent_is_literal(cache_db):
    """搜索 "%" 只能匹配字面量含 "%" 的记录，不能匹配全部记录。"""
    _seed_cache(cache_db)
    rows = cache_db.get_videos(search="%")
    assert len(rows) == 1
    assert rows[0]["title"] == "50% 优惠"
    # 计数与列表口径必须一致（分页 total 不能对不上）
    assert cache_db.count_videos(search="%") == 1


def test_cache_search_underscore_is_not_wildcard(cache_db):
    """搜索 "_" 不能被当作单字符通配符（否则会匹配所有含任意字符的记录）。"""
    _seed_cache(cache_db)
    assert cache_db.get_videos(search="_") == []
    assert cache_db.count_videos(search="_") == 0


def test_cache_search_backslash_is_escaped(cache_db):
    """搜索反斜杠本身不得破坏 LIKE 语法（转义符自身需先转义）。"""
    _seed_cache(cache_db)
    rows = cache_db.get_videos(search="\\")
    assert len(rows) == 0
    assert cache_db.count_videos(search="\\") == 0


# ---------- 缺陷 3：抖音时长毫秒边界 ----------


@pytest.mark.parametrize(
    "duration_ms,expected_sec",
    [
        (1000, 1),      # 1 秒短视频：原判定漏掉 1000 本身，会算成 1000 秒
        (1500, 1),
        (15000, 15),
        (59900, 59),
    ],
)
def test_douyin_duration_ms_converted_to_seconds(duration_ms, expected_sec):
    """抖音 video.duration 是毫秒，须换算成秒；1000 边界必须命中换算分支。"""
    import douyin

    parser = douyin.DouyinParser.__new__(douyin.DouyinParser)
    result = parser._build_result(
        {"desc": "t", "video": {"duration": duration_ms, "play_addr": {"url_list": []}}},
        "7001234",
    )
    assert result["duration"] == expected_sec


def test_douyin_duration_string_matches_seconds():
    """duration_string 必须与换算后的秒数一致（1 秒视频不能显示成 16:40）。"""
    import douyin

    parser = douyin.DouyinParser.__new__(douyin.DouyinParser)
    result = parser._build_result(
        {"desc": "t", "video": {"duration": 1000, "play_addr": {"url_list": []}}},
        "7001234",
    )
    assert result["duration_string"] == "0:01"


def test_douyin_missing_duration_defaults_to_zero():
    """duration 字段缺失时不得抛异常，时长按 0 处理。"""
    import douyin

    parser = douyin.DouyinParser.__new__(douyin.DouyinParser)
    result = parser._build_result({"desc": "t", "video": {}}, "7001234")
    assert result["duration"] == 0
    assert result["duration_string"] == "00:00"
