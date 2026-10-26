"""回归：缓存状态/热门对不存在记录返回 False、expires_at 统一为 UTC、
抖音媒体地址公网校验、缩略图代理按原主机名做 SNI/证书校验。"""
import os
import sys
import tempfile
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import video_cache_db
from video_cache_db import VideoCacheDB, _to_utc_iso
import douyin


@pytest.fixture()
def db(tmp_path):
    video_cache_db.VIDEO_CACHE_DB_PATH = str(tmp_path / "vc.db")
    return VideoCacheDB()


def _save(db, url):
    db.save_video({
        "url": url,
        "video_info": {"platform": "youtube", "video_id": "a", "title": "t"},
        "metadata": {},
        "success": True,
    })


def test_missing_record_returns_false(db):
    assert db.mark_as_hot("https://none.test/v") is False
    assert db.update_cache_status("https://none.test/v", "expired") is False


def test_existing_record_returns_true(db):
    _save(db, "https://ok.test/v")
    assert db.mark_as_hot("https://ok.test/v") is True
    assert db.update_cache_status("https://ok.test/v", "active") is True


def test_expires_at_normalized_to_utc(db):
    assert _to_utc_iso("2030-01-01T08:00:00+08:00") == "2030-01-01T00:00:00+00:00"
    assert _to_utc_iso("2030-01-01T00:00:00Z") == "2030-01-01T00:00:00+00:00"
    assert _to_utc_iso("2030-01-01T00:00:00") == "2030-01-01T00:00:00+00:00"
    with pytest.raises(ValueError):
        _to_utc_iso("not-a-date")
    _save(db, "https://tz.test/v")
    db.update_cache_status("https://tz.test/v", "active", "2099-01-01T08:00:00+08:00")
    assert db.get_video("https://tz.test/v")["cache_expires_at"] == "2099-01-01T00:00:00+00:00"
    assert db.cleanup_expired() == 0


def _fake_getaddrinfo(addr):
    return lambda *a, **k: [(None, None, None, None, (addr, 0))]


@pytest.mark.parametrize("addr", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::ffff:127.0.0.1", "0.0.0.0"])
def test_douyin_media_url_rejects_private(addr):
    with mock.patch.object(douyin.socket, "getaddrinfo", _fake_getaddrinfo(addr)):
        assert douyin._is_public_http_url("https://cdn.example.com/v.mp4") is False


def test_douyin_media_url_allows_public():
    with mock.patch.object(douyin.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34")):
        assert douyin._is_public_http_url("https://cdn.example.com/v.mp4") is True
    assert douyin._is_public_http_url("file:///etc/passwd") is False


def test_thumbnail_proxy_uses_sni_hostname():
    from fastapi.testclient import TestClient
    import httpx
    import main

    captured = {}

    async def fake_get(self, url, headers=None, extensions=None, **kw):
        captured.update(url=url, headers=headers, extensions=extensions)
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"img",
                              request=httpx.Request("GET", url))

    with mock.patch.object(main.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34")), \
            mock.patch.object(httpx.AsyncClient, "get", fake_get):
        resp = TestClient(main.app).get("/api/proxy/thumbnail", params={"url": "https://img.example.com:8443/a.jpg"})

    assert resp.status_code == 200
    assert captured["url"] == "https://93.184.216.34:8443/a.jpg"
    assert captured["headers"]["Host"] == "img.example.com:8443"
    assert captured["extensions"] == {"sni_hostname": "img.example.com"}
