"""
视频缓存数据库模块

提供视频解析数据的持久化存储、缓存规则管理与解析日志能力。
本文件补齐自原 `VIDEO_CACHE_SYSTEM_IMPLEMENTATION.md` 描述的 `video_cache_db.py`
（原源码缺失，导致 /api/video-cache/* 全部 503）。此处按 api_video_cache.py、
video_cache_manager.py 与 tests/test_video_cache.py 的调用契约重建。

对外暴露：
- VIDEO_CACHE_DB_PATH       模块级变量（可被测试覆盖）
- get_video_cache_db_path() 返回当前数据库路径
- video_cache_db            VideoCacheDB 单例（api_video_cache / video_cache_manager 直接引用）
- VideoCacheDB 类           数据库模型与操作方法
"""

import os
import json
import sqlite3
import hashlib
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

__all__ = [
    "VIDEO_CACHE_DB_PATH",
    "get_video_cache_db_path",
    "normalize_url",
    "normalize_platform",
    "VideoCacheDB",
    "video_cache_db",
]

VIDEO_CACHE_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "video_cache.db")


def get_video_cache_db_path() -> str:
    """返回当前视频缓存数据库路径（供测试覆盖 VIDEO_CACHE_DB_PATH 后读取）。"""
    return VIDEO_CACHE_DB_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_utc_iso(value: str) -> str:
    """把外部传入的时间字符串规范为 UTC isoformat（无时区视为 UTC），
    使 cache_expires_at 与 _now() 格式一致、可按字符串比较。非法格式抛 ValueError。"""
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def normalize_url(url: str) -> str:
    """URL 归一化：与 history 表使用同一口径（database.canonical_video_url）。

    原实现只小写 scheme/netloc，保留 www. 与 fragment，会导致同一视频在
    video_cache 与 history 两表的键值不同（例如 http://www.x.com/v#f 与
    https://x.com/v 被当成两条），缓存去重键与历史去重键错位。
    这里统一复用 canonical_video_url：纯数字抖音 ID 也会补全为完整链接。
    """
    try:
        from database import canonical_video_url
    except ImportError:
        # database 模块不可用时退回宽松归一化，避免整个缓存模块无法导入
        from urllib.parse import urlparse, urlunparse

        p = urlparse(url or "")
        return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path, p.params, p.query, p.fragment))
    return canonical_video_url(url)


def normalize_platform(platform) -> str:
    """平台标识归一化：与 history / 后台筛选 / 缓存规则共用 database.canonical_platform 口径。

    入库值此前直接取 info['platform']：抖音专用解析写中文 "抖音"，yt-dlp 写
    extractor 名（"BiliBili" / "TikTok" …，大小写不固定），而后台平台筛选与缓存
    规则用的是小写 slug，三者互不相等 → 按平台筛选永远筛不出数据、按平台配置的
    缓存规则永远不命中。统一在此收敛，写入与查询都用同一口径。
    """
    try:
        from database import canonical_platform
    except ImportError:
        return (platform or "").strip().lower() if platform is not None else ""
    return canonical_platform(platform)


def _url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


class VideoCacheDB:
    """视频缓存数据库操作封装（SQLite，参数化查询防注入）。"""

    def __init__(self, db_path: str | None = None):
        # 读取模块级 VIDEO_CACHE_DB_PATH（测试会先覆盖该变量再构造实例）
        self.db_path = db_path or VIDEO_CACHE_DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    # ---------- 底层连接 ----------
    @contextmanager
    def _conn(self):
        # timeout=30：api_video_cache 的路由已改为同步 def（FastAPI 放进线程池），
        # 并发写同一张表时若无 busy_timeout 会直接抛 "database is locked"。
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
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

                CREATE INDEX IF NOT EXISTS idx_vc_url_hash ON video_cache(url_hash);
                CREATE INDEX IF NOT EXISTS idx_vc_platform ON video_cache(platform);
                CREATE INDEX IF NOT EXISTS idx_vc_cache_status ON video_cache(cache_status);
                CREATE INDEX IF NOT EXISTS idx_vc_cache_expires ON video_cache(cache_expires_at);
                CREATE INDEX IF NOT EXISTS idx_vc_is_hot ON video_cache(is_hot);

                CREATE TABLE IF NOT EXISTS parse_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT,
                    task_id TEXT,
                    status TEXT,
                    progress INTEGER DEFAULT 0,
                    stage TEXT,
                    message TEXT,
                    success INTEGER DEFAULT 0,
                    error_message TEXT,
                    error_code TEXT,
                    duration_ms INTEGER DEFAULT 0,
                    retry_count INTEGER DEFAULT 0,
                    created_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_pl_url ON parse_logs(url);
                CREATE INDEX IF NOT EXISTS idx_pl_task ON parse_logs(task_id);

                CREATE TABLE IF NOT EXISTS cache_rules (
                    rule_name TEXT PRIMARY KEY,
                    rule_type TEXT,
                    platform TEXT,
                    url_pattern TEXT,
                    quality TEXT,
                    min_duration REAL,
                    max_duration REAL,
                    ttl_seconds INTEGER DEFAULT 86400,
                    priority INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    description TEXT
                );
                """
            )
            self._migrate_url_normalization(conn)
            self._migrate_platform_normalization(conn)
            self._seed_default_cache_rules(conn)

    def _migrate_platform_normalization(self, conn):
        """把存量 platform 列改写为统一的小写 slug 口径（幂等）。

        老数据里 platform 存的是解析器原始写法（"抖音" / "BiliBili" / "YouTube"），
        与后台筛选、缓存规则使用的小写 slug 不一致，导致按平台筛选空结果、
        按平台配置的缓存规则永不命中。只改写有变化的行，重复执行无副作用。
        """
        rows = conn.execute(
            "SELECT DISTINCT platform FROM video_cache WHERE platform IS NOT NULL AND platform != ''"
        ).fetchall()
        for row in rows:
            old = row["platform"]
            new = normalize_platform(old)
            if new and new != old:
                conn.execute("UPDATE video_cache SET platform=? WHERE platform=?", (new, old))

    # 内置默认缓存规则。
    # 规则表此前恒空 —— get_cache_ttl 遍历不到任何规则，永远回退到硬编码的 86400，
    # "按平台/时长差异化 TTL" 这套机制完全空转。这里在表为空时写入一组默认规则，
    # 让规则匹配真正生效（优先级越高越先命中；duration 为 0 表示不限）。
    DEFAULT_CACHE_RULES = (
        {
            "rule_name": "default",
            "rule_type": "ttl",
            "platform": "",
            "url_pattern": "",
            "quality": "",
            "min_duration": 0,
            "max_duration": 0,
            "ttl_seconds": 86400,
            "priority": 0,
            "is_active": 1,
            "description": "默认缓存时长 24 小时",
        },
        {
            "rule_name": "short_video",
            "rule_type": "ttl",
            "platform": "",
            "url_pattern": "",
            "quality": "",
            "min_duration": 0,
            "max_duration": 300,
            "ttl_seconds": 21600,
            "priority": 10,
            "is_active": 1,
            "description": "短视频（≤5 分钟）缓存 6 小时",
        },
        {
            "rule_name": "long_video",
            "rule_type": "ttl",
            "platform": "",
            "url_pattern": "",
            "quality": "",
            "min_duration": 1800,
            "max_duration": 0,
            "ttl_seconds": 259200,
            "priority": 10,
            "is_active": 1,
            "description": "长视频（≥30 分钟）缓存 3 天",
        },
    )

    def _seed_default_cache_rules(self, conn):
        """仅在 cache_rules 为空时写入内置规则。

        刻意不做"每次启动都补齐"：用户删掉的规则不该在重启后复活；
        只有整表为空（全新部署）时才播种默认规则。
        """
        count = conn.execute("SELECT COUNT(*) FROM cache_rules").fetchone()[0]
        if count:
            return
        for rule in self.DEFAULT_CACHE_RULES:
            conn.execute(
                """
                INSERT OR IGNORE INTO cache_rules (
                    rule_name, rule_type, platform, url_pattern, quality,
                    min_duration, max_duration, ttl_seconds, priority, is_active, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule["rule_name"], rule["rule_type"], rule["platform"],
                    rule["url_pattern"], rule["quality"], rule["min_duration"],
                    rule["max_duration"], rule["ttl_seconds"], rule["priority"],
                    rule["is_active"], rule["description"],
                ),
            )

    def _migrate_url_normalization(self, conn):
        """把存量记录的 video_url / url_hash 重写为当前归一化口径。

        背景：早期 normalize_url 只小写 scheme/netloc（保留 www. 与 fragment），
        与 history 表口径不同，导致同一视频在两表对不上。后来统一为
        canonical_video_url（强制 https、去 www.、去 fragment、纯数字补全），
        老记录的键值格式就与新代码不一致了 —— 用新口径查询会匹配不上。

        归一化后撞到同一 URL 的多条记录会合并成一条（保留 id 最小的，
        命中数累加、热门标记取或），再改写保留者的 video_url / url_hash。
        顺序很关键：必须先删除重复行再改写保留者，否则改写时会撞上
        UNIQUE(video_url) 约束，导致整个迁移回滚。
        """
        rows = conn.execute(
            "SELECT id, video_url, url_hash, cache_hit_count, is_hot FROM video_cache ORDER BY id"
        ).fetchall()
        if not rows:
            return

        # 按归一化后的 URL 分群
        groups: dict[str, list] = {}
        for row in rows:
            groups.setdefault(normalize_url(row["video_url"]), []).append(row)

        for new_url, group in groups.items():
            keeper = group[0]  # id 最小的那条
            if len(group) > 1:
                total_hits = sum(r["cache_hit_count"] or 0 for r in group)
                hot = 1 if any(r["is_hot"] for r in group) else 0
                for r in group[1:]:
                    conn.execute("DELETE FROM video_cache WHERE id = ?", (r["id"],))
                conn.execute(
                    "UPDATE video_cache SET cache_hit_count = ?, is_hot = ? WHERE id = ?",
                    (total_hits, hot, keeper["id"]),
                )
            new_hash = _url_hash(keeper["video_url"])
            if keeper["video_url"] != new_url or keeper["url_hash"] != new_hash:
                conn.execute(
                    "UPDATE video_cache SET video_url = ?, url_hash = ? WHERE id = ?",
                    (new_url, new_hash, keeper["id"]),
                )

    # ---------- 视频缓存 CRUD ----------
    # 核心字段（重复 URL 时仅更新这些列，cache_status / cache_hit_count / is_hot 保持原值）
    _CORE_COLS = (
        "url_hash", "platform", "video_id", "title", "description", "uploader",
        "thumbnail_url", "duration", "width", "height", "fps", "codec", "bitrate",
        "file_size", "format", "quality", "parse_timestamp", "parse_success",
        "parse_error", "direct_url", "download_url", "available_formats",
        "cache_expires_at", "updated_at",
    )

    def save_video(self, video_data: dict, ttl_seconds: int | None = None) -> bool:
        """保存/更新一条视频缓存。重复 URL 做字段更新（保留命中数与热门标记）。

        ttl_seconds 由调用方按缓存规则计算后传入（video_cache_manager.get_cache_ttl）；
        未传或非法时回退默认 1 天，保证缓存始终具备时间生命周期，避免无限膨胀。"""
        url = (video_data.get("url") or "").strip()
        if not url:
            return False
        # 归一化后再入库：video_url 列、url_hash 去重键与 history 表保持同一口径，
        # 否则同一视频会以不同形态存成多条记录（唯一约束只对完全相同的字符串生效）。
        url = normalize_url(url)
        if not url:
            return False

        info = video_data.get("video_info") or {}
        meta = video_data.get("metadata") or {}
        success = 1 if video_data.get("success", True) else 0

        # 平台名统一收敛为小写 slug 后再入库，否则后台按平台筛选与缓存规则都匹配不上
        # （抖音专用解析给 "抖音"，yt-dlp 给 "BiliBili"/"TikTok" 这类大小写不固定的名字）。
        platform = normalize_platform(info.get("platform"))
        video_id = info.get("video_id")
        title = info.get("title")
        description = info.get("description")
        uploader = info.get("uploader")
        thumbnail = info.get("thumbnail") or info.get("thumbnail_url")
        duration = meta.get("duration", 0) or 0
        width = meta.get("width", 0) or 0
        height = meta.get("height", 0) or 0
        fps = meta.get("fps", 0) or 0
        codec = meta.get("codec")
        bitrate = meta.get("bitrate", 0) or 0
        file_size = meta.get("file_size", 0) or 0
        fmt = meta.get("format")
        quality = meta.get("quality")
        direct_url = info.get("direct_url") or meta.get("direct_url")
        download_url = info.get("download_url") or meta.get("download_url")
        formats = info.get("formats")
        available_formats = json.dumps(formats, ensure_ascii=False) if isinstance(formats, (list, dict)) else None
        # TTL：优先用调用方按缓存规则算出的值，非法/缺省时回退 1 天（与 get_cache_ttl 默认一致）。
        try:
            effective_ttl = int(ttl_seconds) if ttl_seconds else 86400
        except (TypeError, ValueError):
            effective_ttl = 86400
        if effective_ttl <= 0:
            effective_ttl = 86400
        # 统一用 UTC 字符串，避免时区混用导致比较错乱。
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=effective_ttl)).isoformat()

        now = _now()
        # 与 _CORE_COLS 一一对应的参数
        params = (
            _url_hash(url), platform, video_id, title, description, uploader, thumbnail,
            duration, width, height, fps, codec, bitrate, file_size, fmt, quality,
            now, success, video_data.get("error"), direct_url, download_url,
            available_formats, expires_at, now,
        )

        cols_sql = ", ".join(self._CORE_COLS)
        placeholders = ", ".join(["?"] * len(self._CORE_COLS))
        # 重新保存即刷新了数据与过期时间，状态需重置为 active，否则旧的 expired 状态
        # 会让刚写入的数据被 cleanup_expired 立即删除。
        update_sql = ", ".join(f"{c}=excluded.{c}" for c in self._CORE_COLS) + ", cache_status='active'"

        with self._conn() as conn:
            # 幂等 upsert：并发同 URL 写入时由唯一约束 + ON CONFLICT 保证只成功一次，
            # 不会因 SELECT 后再 INSERT 引发 IntegrityError 500。
            conn.execute(
                f"INSERT INTO video_cache (video_url, {cols_sql}, created_at) "
                f"VALUES (?, {placeholders}, ?) "
                f"ON CONFLICT(video_url) DO UPDATE SET {update_sql}",
                (url, *params, now),
            )
        return True

    def get_video(self, url: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM video_cache WHERE video_url=?", (normalize_url(url),)
            ).fetchone()
        return dict(row) if row else None

    def _build_filters(
        self,
        cache_status: str | None = None,
        platform: str | None = None,
        search: str | None = None,
        hot_only: bool = False,
    ) -> tuple[str, list]:
        """根据筛选条件构建 WHERE 子句与参数，供列表查询与计数查询复用，
        避免两处条件不一致导致分页 total 与实际条数对不上。"""
        clauses = []
        params: list = []
        if cache_status:
            clauses.append("cache_status=?")
            params.append(cache_status)
        if platform:
            # 平台名大小写不敏感：存量数据里还有 "BiliBili" / "YouTube" 这类原始写法，
            # 而筛选参数是前端下拉的小写 slug，直接等值比较会永远筛不出数据。
            clauses.append("LOWER(COALESCE(platform, ''))=?")
            params.append(normalize_platform(platform))
        if hot_only:
            clauses.append("is_hot=1")
        if search:
            clauses.append("(title LIKE ? OR video_url LIKE ? OR uploader LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    def get_videos(
        self,
        cache_status: str | None = None,
        platform: str | None = None,
        search: str | None = None,
        hot_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        where, params = self._build_filters(cache_status, platform, search, hot_only)
        sql = (
            f"SELECT * FROM video_cache{where} ORDER BY created_at DESC, id DESC "
            f"LIMIT ? OFFSET ?"
        )
        params.extend([int(limit), int(offset)])
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def count_videos(
        self,
        cache_status: str | None = None,
        platform: str | None = None,
        search: str | None = None,
        hot_only: bool = False,
    ) -> int:
        """返回与筛选条件匹配的真实总条数（分页 total 契约）。"""
        where, params = self._build_filters(cache_status, platform, search, hot_only)
        with self._conn() as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM video_cache{where}", params).fetchone()
        return int(row[0])

    def increment_hit_count(self, url: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE video_cache SET cache_hit_count = cache_hit_count + 1, "
                "last_access_at=? WHERE video_url=?",
                (_now(), normalize_url(url)),
            )

    def increment_hit_and_mark_hot(self, url: str, threshold: int) -> bool:
        """原子地自增命中数，并在达到阈值时标记为热门。

        用单条 UPDATE 完成「自增 + 条件标记」，避免原先 read-then-write 的三步
        （increment → 重新 SELECT 判断阈值 → mark）产生的竞态：并发命中时
        可能重复判定或漏判热门。返回是否标记了热门。
        """
        key = normalize_url(url)
        with self._conn() as conn:
            conn.execute(
                "UPDATE video_cache SET cache_hit_count = cache_hit_count + 1, "
                "last_access_at=? WHERE video_url=?",
                (_now(), key),
            )
            cur = conn.execute(
                "UPDATE video_cache SET is_hot=1, updated_at=? "
                "WHERE video_url=? AND is_hot=0 AND cache_hit_count >= ?",
                (_now(), key, int(threshold)),
            )
        return cur.rowcount > 0

    def update_cache_status(self, url: str, status: str, expires_at: str | None = None) -> bool:
        if expires_at:
            # 统一转成带 UTC 时区的 isoformat，保证与 _now() 按字符串比较时语义正确
            expires_at = _to_utc_iso(expires_at)
        key = normalize_url(url)
        with self._conn() as conn:
            if expires_at:
                cur = conn.execute(
                    "UPDATE video_cache SET cache_status=?, cache_expires_at=?, updated_at=? "
                    "WHERE video_url=?",
                    (status, expires_at, _now(), key),
                )
            else:
                # 不传 expires_at 时：置为 active 必须同时刷新过期时间，
                # 否则会保留旧的（可能已过期）到期时间，缓存刚被激活就被
                # cleanup_expired 判定过期删除。其它状态沿用原到期时间。
                if status == "active":
                    cur = conn.execute(
                        "UPDATE video_cache SET cache_status=?, cache_expires_at=?, updated_at=? "
                        "WHERE video_url=?",
                        (status, _now(), _now(), key),
                    )
                else:
                    cur = conn.execute(
                        "UPDATE video_cache SET cache_status=?, updated_at=? WHERE video_url=?",
                        (status, _now(), key),
                    )
        return cur.rowcount > 0

    def delete_video(self, url: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM video_cache WHERE video_url=?", (normalize_url(url),))
        return cur.rowcount > 0

    def mark_as_hot(self, url: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE video_cache SET is_hot=1, updated_at=? WHERE video_url=?",
                (_now(), normalize_url(url)),
            )
        return cur.rowcount > 0

    def get_stats(self) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_videos,
                    COALESCE(SUM(CASE WHEN cache_status='active' THEN 1 ELSE 0 END), 0) AS active_cache,
                    COALESCE(SUM(CASE WHEN cache_status='expired' THEN 1 ELSE 0 END), 0) AS expired_cache,
                    COALESCE(SUM(is_hot), 0) AS hot_cache,
                    COALESCE(SUM(cache_hit_count), 0) AS total_cache_hits
                FROM video_cache
                """
            ).fetchone()
            platform_rows = conn.execute(
                "SELECT COALESCE(platform, 'unknown') AS platform, COUNT(*) AS cnt "
                "FROM video_cache GROUP BY COALESCE(platform, 'unknown')"
            ).fetchall()
        stats = dict(row)
        stats["by_platform"] = {r["platform"]: r["cnt"] for r in platform_rows}
        return stats

    def cleanup_expired(self) -> int:
        now = _now()
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM video_cache WHERE cache_status='expired' "
                "OR (cache_expires_at IS NOT NULL AND cache_expires_at < ?)",
                (now,),
            )
        return cur.rowcount

    # ---------- 缓存规则 ----------
    def get_cache_rules(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM cache_rules ORDER BY priority DESC, rule_name"
            ).fetchall()
        return [dict(r) for r in rows]

    def save_cache_rule(self, rule_data: dict) -> bool:
        rule_name = (rule_data.get("rule_name") or "").strip()
        if not rule_name:
            return False
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO cache_rules (
                    rule_name, rule_type, platform, url_pattern, quality,
                    min_duration, max_duration, ttl_seconds, priority, is_active, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rule_name) DO UPDATE SET
                    rule_type=excluded.rule_type, platform=excluded.platform,
                    url_pattern=excluded.url_pattern, quality=excluded.quality,
                    min_duration=excluded.min_duration, max_duration=excluded.max_duration,
                    ttl_seconds=excluded.ttl_seconds, priority=excluded.priority,
                    is_active=excluded.is_active, description=excluded.description
                """,
                (
                    rule_name,
                    rule_data.get("rule_type"),
                    # 规则里的平台名同样收敛为小写 slug，与管理台下拉/入库数据同一口径，
                    # 否则规则里写 "BiliBili"、数据里存 "bilibili" 时规则永远不命中。
                    normalize_platform(rule_data.get("platform")),
                    rule_data.get("url_pattern"),
                    rule_data.get("quality"),
                    rule_data.get("min_duration"),
                    rule_data.get("max_duration"),
                    rule_data.get("ttl_seconds", 86400),
                    rule_data.get("priority", 0),
                    1 if rule_data.get("is_active", True) else 0,
                    rule_data.get("description"),
                ),
            )
        return True

    def delete_cache_rule(self, rule_name: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM cache_rules WHERE rule_name=?", (rule_name,))
        return cur.rowcount > 0

    # ---------- 解析日志 ----------
    def get_parse_logs(self, limit: int = 100) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM parse_logs ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [dict(r) for r in rows]

    def save_parse_log(self, log_data: dict) -> bool:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO parse_logs (
                    url, task_id, status, progress, stage, message, success,
                    error_message, error_code, duration_ms, retry_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_data.get("url"),
                    log_data.get("task_id"),
                    log_data.get("status"),
                    log_data.get("progress", 0),
                    log_data.get("stage"),
                    log_data.get("message"),
                    1 if log_data.get("success") else 0,
                    log_data.get("error_message"),
                    log_data.get("error_code"),
                    log_data.get("duration_ms", 0),
                    log_data.get("retry_count", 0),
                    _now(),
                ),
            )
        return True


# 模块级单例（api_video_cache.py 与 video_cache_manager.py 直接引用）
video_cache_db = VideoCacheDB()
