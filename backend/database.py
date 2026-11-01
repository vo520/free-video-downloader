import os
import logging
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit
import json

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "app.db")


def get_db_path():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return DB_PATH


@contextmanager
def get_db():
    # timeout=30 + busy_timeout=30000：与 video_cache_db.py 保持一致。
    # 本库的写操作（历史 upsert、总结配额扣减、订单状态翻转）会在 FastAPI
    # 线程池里并发执行，WAL 模式下写-写仍互斥；没有 busy_timeout 时并发写会
    # 立刻抛 "database is locked"（历史丢失 / 配额扣减 500），有了它则等待至多 30s。
    conn = sqlite3.connect(get_db_path(), timeout=30)
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


def init_db():
    """初始化数据库表结构"""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_vip INTEGER DEFAULT 0,
                vip_expire_at TEXT,
                daily_summary_count INTEGER DEFAULT 0,
                last_summary_date TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                currency TEXT DEFAULT 'cny',
                status TEXT DEFAULT 'pending',
                plan_type TEXT DEFAULT 'monthly',
                stripe_session_id TEXT UNIQUE,
                stripe_payment_intent_id TEXT,
                paid_at TEXT,
                fail_reason TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
            CREATE INDEX IF NOT EXISTS idx_orders_order_no ON orders(order_no);
            CREATE INDEX IF NOT EXISTS idx_orders_stripe_session_id ON orders(stripe_session_id);

            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                video_url TEXT,
                title TEXT,
                platform TEXT,
                thumbnail TEXT,
                snapshot TEXT,
                extra TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_history_user_id ON history(user_id);
            CREATE INDEX IF NOT EXISTS idx_history_user_type ON history(user_id, type);
            -- 去重索引不在这里建：下方迁移会用 UNIQUE 版本 uniq_history_user_type_url。
            -- 若此处再建一个同列的非唯一索引，迁移会在同一次启动里把它 DROP 掉，
            -- 等于每次启动都白白对整表做一次索引重建。
        """)
        # 历史去重加固迁移（幂等，init_db 每次启动安全重跑）：
        # ① 按「归一化 URL」分组，每组保留 id 最大（最新）一条，其余删除（先删后改，
        #    避免 UPDATE 时被即将建立的唯一索引拦下；同时让 http/www/#frag 等同源变体归一去重）；
        # ② 将保留行的 video_url 改写为归一化形式（避免与新归一化写入产生重复）；
        # ③ 建唯一索引，使 add_history 的 upsert 在 DB 层原子去重，消除并发竞态。
        try:
            # 兼容老库：若 history 表没有 snapshot 列则补上（重复执行会被 sqlite 报 duplicate column，
            # 被外层 try/except 兜底，不影响后续迁移）。新装环境已在 CREATE TABLE 里含 snapshot，无需此步。
            try:
                conn.execute("ALTER TABLE history ADD COLUMN snapshot TEXT")
            except Exception:
                pass
            rows = conn.execute("SELECT id, user_id, type, video_url FROM history").fetchall()
            groups = {}
            for r in rows:
                key = (r["user_id"], r["type"], canonical_video_url(r["video_url"]))
                groups.setdefault(key, []).append(r["id"])
            delete_ids = []
            for ids in groups.values():
                if len(ids) > 1:
                    delete_ids.extend(sorted(ids, reverse=True)[1:])  # 保留最大 id
            if delete_ids:
                placeholders = ",".join("?" * len(delete_ids))
                conn.execute(f"DELETE FROM history WHERE id IN ({placeholders})", delete_ids)
            for r in rows:
                norm = canonical_video_url(r["video_url"])
                if norm != r["video_url"]:
                    conn.execute("UPDATE history SET video_url=? WHERE id=?", (norm, r["id"]))
            conn.execute("DROP INDEX IF EXISTS idx_history_user_type_url")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uniq_history_user_type_url "
                "ON history(user_id, type, video_url)"
            )
        except Exception as e:
            logging.warning("history 去重迁移跳过: %s", e)

        # 兼容老库：orders 表补 fail_reason 列（记录支付失败回滚的原因）。
        # CREATE TABLE IF NOT EXISTS 不会给已存在的表加列，需显式 ALTER。
        try:
            conn.execute("ALTER TABLE orders ADD COLUMN fail_reason TEXT")
        except Exception:
            pass


FREE_DAILY_SUMMARY_LIMIT = 3


def get_user_by_email(email: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def create_user(email: str, password_hash: str) -> dict:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, password_hash),
        )
        return {"id": cursor.lastrowid, "email": email}


def _normalize_video_url(url):
    """归一化视频 URL 以便去重：小写 host、强制 https、去除 www. 前缀与 fragment。

    保留 query（部分平台把视频标识放在 query 中，不可随意丢弃）；仅做跨平台通用的安全归一化，
    使 `http://www.x.com/v#frag` 与 `https://x.com/v` 被识别为同一视频。失败时原样返回。
    """
    if not url or not isinstance(url, str):
        return url
    try:
        p = urlsplit(url.strip())
        if not p.netloc:
            return url.strip()
        netloc = p.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        # 重组：scheme 强制 https，丢弃 fragment，保留 path/query
        return urlunsplit(("https", netloc, p.path, p.query, ""))
    except Exception:
        return url


def canonical_video_url(url):
    """把用户输入的链接归一为「该视频的唯一标识形式」，作为跨表去重的唯一口径。

    规则（与 _normalize_video_url 保持一致，并额外处理纯数字抖音 ID）：
    - 纯数字的抖音视频 ID 补全为 https://www.douyin.com/video/{id}
      （与 /api/parse 的处理一致，否则同一视频在 history 与 video_cache 两表键值不同）
    - 小写 host、强制 https、去除 www. 前缀与 fragment，保留 path/query

    history 与 video_cache 两张表都必须用本函数归一，否则同一视频在两表对不上，
    缓存去重键与历史去重键也会错位。失败时原样返回。
    """
    if not url or not isinstance(url, str):
        return url
    raw = url.strip()
    if raw.isdigit():
        raw = f"https://www.douyin.com/video/{raw}"
    return _normalize_video_url(raw)


# 平台标识归一化别名表：只有「中文名」与「英文 slug」同时存在时才需要显式映射。
# 抖音专用解析返回中文 "抖音"，而后台筛选 / 缓存规则用的是英文 slug（douyin/bilibili/...）。
_PLATFORM_ALIASES = {
    "抖音": "douyin",
    "哔哩哔哩": "bilibili",
    "b站": "bilibili",
}


def canonical_platform(platform) -> str:
    """把平台标识归一为小写 slug（youtube/bilibili/douyin/twitter/...）。

    平台名在三处写法不同：抖音专用解析返回中文 "抖音"；yt-dlp 返回 extractor 名
    （"youtube" / "BiliBili" / "TikTok"…，大小写不固定）；而后台平台筛选与缓存规则
    用的是小写 slug。三者互不相等时，后台按平台筛选永远筛不出数据、按平台配置的
    缓存规则也永远不命中。这里统一收敛到小写 slug，入库 / 筛选 / 规则匹配共用同一口径。

    未识别的平台名按小写原样保留（如 "tiktok"），不丢信息。
    """
    if platform is None:
        return ""
    raw = str(platform).strip()
    if not raw:
        return ""
    lowered = raw.lower()
    return _PLATFORM_ALIASES.get(lowered, lowered)


def add_history(user_id, htype, video_url='', title='', platform='', thumbnail='', extra=None, snapshot=None):
    """记录/更新一条用户历史（解析/下载/总结）。

    - user_id 为空（未登录）或 video_url 为空时直接跳过（不落库、不落空记录）。
    - video_url 先归一化，再按 (user_id, type, video_url) 去重：已存在则更新
      （刷新标题/平台/缩略图/extra/snapshot，并把 created_at 置为当前时间顶到最前），
      不存在才插入。这样不同 URL 形态（www/http/#fragment）的同视频也会归一为一条。
    - snapshot：解析历史的完整结果 JSON（含 formats/duration/uploader 等），使历史回看
      不必重新调 yt-dlp；download/summary 类型无需该字段，传 None 即可。
    - 落库异常仅记录 warning（不中断主流程），便于排障时定位"为何历史没写"，best-effort 不变。

    返回 True/None。
    """
    if not user_id:
        return None
    # 用 canonical_video_url（而非 _normalize_video_url）：裸数字抖音 ID 也要补全为
    # 完整链接，否则同一视频在 history 与 video_cache 两表的去重键对不上
    # （video_cache 用的是 canonical_video_url 口径）。
    video_url = canonical_video_url(video_url)
    if not video_url:
        return None
    try:
        extra_json = json.dumps(extra, ensure_ascii=False) if extra is not None else None
    except (TypeError, ValueError):
        extra_json = None
    try:
        snapshot_json = json.dumps(snapshot, ensure_ascii=False) if snapshot is not None else None
    except (TypeError, ValueError):
        snapshot_json = None
    try:
        with get_db() as conn:
            # 原子 upsert：依赖 (user_id,type,video_url) 唯一索引，并发写入不会重复；
            # 已存在则刷新字段并把 created_at 顶到最前（最近使用语义）。
            # 替代原先「先 SELECT 再 INSERT/UPDATE」的读后写，消除两个并发事务同时
            # 判定「不存在」而各 INSERT 一条导致重复行的竞态。
            conn.execute(
                """INSERT INTO history (user_id, type, video_url, title, platform, thumbnail, extra, snapshot, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(user_id, type, video_url) DO UPDATE SET
                     title=excluded.title,
                     platform=excluded.platform,
                     thumbnail=excluded.thumbnail,
                    extra=excluded.extra,
                     snapshot=excluded.snapshot,
                     created_at=datetime('now')""",
                (user_id, htype, video_url, title, platform, thumbnail, extra_json, snapshot_json),
            )
            return True
    except Exception as e:
        logging.warning(
            "add_history 失败 user=%s type=%s url=%s: %s", user_id, htype, video_url, e
        )
        return None


def get_history(user_id, htype=None, limit=50, offset=0, search=None):
    """读取当前用户的历史记录，按时间倒序。返回 (rows, total)。

    search：按标题 / 平台 / 链接做模糊匹配（服务端过滤）。
    前端原先只能在「已加载的一页」里做本地过滤，历史超过 100 条时搜索形同虚设，
    这里把过滤下推到 SQL，保证搜索覆盖全量历史。
    """
    if not user_id:
        return [], 0
    with get_db() as conn:
        clauses = ["user_id = ?"]
        params = [user_id]
        if htype:
            clauses.append("type = ?")
            params.append(htype)
        keyword = (search or "").strip()
        if keyword:
            # 转义 LIKE 通配符：否则用户搜 "%" 会匹配全部记录、"_" 会变成单字符通配。
            escaped = (
                keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            like = f"%{escaped}%"
            clauses.append(
                "(title LIKE ? ESCAPE '\\' OR platform LIKE ? ESCAPE '\\' "
                "OR video_url LIKE ? ESCAPE '\\')"
            )
            params.extend([like, like, like])
        where = " AND ".join(clauses)
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM history WHERE {where}", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM history WHERE {where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            # extra 在库中存为 JSON 字符串，直接解析为对象返回，避免前端/调用方再做 JSON.parse，
            # 同时保证 extra 字段契约统一（解析失败或为空时置 None）。
            raw = d.get("extra")
            if raw:
                try:
                    d["extra"] = json.loads(raw)
                except (TypeError, ValueError):
                    d["extra"] = None
            else:
                d["extra"] = None
            # snapshot 同 extra：解析历史的完整 videoData JSON，使历史回看不必重新解析。
            raw = d.get("snapshot")
            if raw:
                try:
                    d["snapshot"] = json.loads(raw)
                except (TypeError, ValueError):
                    d["snapshot"] = None
            else:
                d["snapshot"] = None
            result.append(d)
        return result, total


def delete_history(hid, user_id):
    """删除单条历史，校验归属当前用户。返回是否删除成功。"""
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM history WHERE id = ? AND user_id = ?", (hid, user_id)
        )
        return cur.rowcount > 0


def clear_history(user_id):
    """清空当前用户全部历史。返回实际删除的条数（0 表示无记录或未登录）。

    原实现只返回布尔值，前端只能用本地列表长度报「已清空 N 条」，
    而服务端删除的是全部类型（parse / download / summary），
    两者数量不一致会让提示误导用户。
    """
    if not user_id:
        return 0
    with get_db() as conn:
        cur = conn.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        return cur.rowcount


def _is_vip_active(user) -> bool:
    """判断用户行当前是否处于有效 VIP 状态（is_vip 且未过期）。

    check_summary_quota（只读）与 check_and_increment_summary（消费）必须用同一口径，
    否则会出现「配额接口说不是 VIP、扣减接口说是 VIP」的不一致。
    """
    if not user["is_vip"] or not user["vip_expire_at"]:
        return False
    try:
        expire_str = user["vip_expire_at"]
        # 缺时区则按 UTC 补全：naive 值与带时区的 now 比较会抛 TypeError
        if "+" in expire_str or "Z" in expire_str:
            expire = datetime.fromisoformat(expire_str.replace("Z", "+00:00"))
        else:
            expire = datetime.fromisoformat(expire_str).replace(tzinfo=timezone.utc)
        return expire > datetime.now(timezone.utc)
    except (ValueError, TypeError):
        return False


def check_summary_quota(user_id: int) -> tuple[bool, int]:
    """只读检查用户是否还有免费 AI 总结额度（不自增计数）。

    返回 (allowed, remaining)。VIP 用户返回 (True, -1) 表示无限制。
    与 check_and_increment_summary 的区别：本函数不消费额度，仅用于"开始前预判"，
    避免无字幕等失败场景白白消耗用户免费次数。
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return False, 0

        if _is_vip_active(user):
            return True, -1  # -1 means unlimited

        if user["last_summary_date"] != today:
            return True, FREE_DAILY_SUMMARY_LIMIT

        current = user["daily_summary_count"]
        if current >= FREE_DAILY_SUMMARY_LIMIT:
            return False, 0

        return True, FREE_DAILY_SUMMARY_LIMIT - current


def check_and_increment_summary(user_id: int) -> tuple[bool, int]:
    """
    检查用户是否可以使用 AI 总结，并自增计数。
    返回 (allowed, remaining_count)。

    并发安全：额度扣减由**单条带条件的 UPDATE** 完成，依赖 rowcount 判定是否放行，
    避免「先 SELECT 再 UPDATE」在并发下被突破日额度的问题。

    跨天重置也放进同一条 UPDATE 的 CASE 表达式里：原先跨天分支无条件
    `SET daily_summary_count = 1`，同一天首批并发请求会互相覆盖计数
    （每个都把自己算成当天第 1 次），实际放行次数会超过每日上限。
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return False, 0

        if _is_vip_active(user):
            return True, -1  # -1 means unlimited

        # 单条原子 UPDATE 同时覆盖「跨天重置」与「同日 +1」两种情况：
        #   CASE  —— 同日则 +1，跨天/首次使用则重置为 1
        #   WHERE —— 同日时要求 count < 上限（否则 rowcount=0 = 已用尽）
        cur = conn.execute(
            "UPDATE users SET "
            "  daily_summary_count = CASE WHEN last_summary_date = ? "
            "    THEN COALESCE(daily_summary_count, 0) + 1 ELSE 1 END, "
            "  last_summary_date = ? "
            "WHERE id = ? "
            "  AND (last_summary_date IS NULL OR last_summary_date <> ? "
            "       OR COALESCE(daily_summary_count, 0) < ?)",
            (today, today, user_id, today, FREE_DAILY_SUMMARY_LIMIT),
        )
        if cur.rowcount == 0:
            # 已达上限（可能刚被其他并发请求占满）
            return False, 0
        # 读取更新后的真实计数用于计算剩余
        updated = conn.execute(
            "SELECT daily_summary_count FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        current = updated["daily_summary_count"] if updated else FREE_DAILY_SUMMARY_LIMIT
        return True, FREE_DAILY_SUMMARY_LIMIT - current


def create_order(user_id: int, order_no: str, amount: int, currency: str = "cny", plan_type: str = "monthly") -> dict:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO orders (order_no, user_id, amount, currency, plan_type) VALUES (?, ?, ?, ?, ?)",
            (order_no, user_id, amount, currency, plan_type),
        )
        return {"order_no": order_no, "user_id": user_id, "amount": amount}


def update_order_stripe_session(order_no: str, session_id: str):
    with get_db() as conn:
        # 与其它订单写入统一用带 UTC 时区的 ISO 格式：
        # datetime('now') 产出 "YYYY-MM-DD HH:MM:SS"（无时区、空格分隔），
        # 与 ISO 格式混在同一列时按字符串比较/排序会得到错误结果。
        conn.execute(
            "UPDATE orders SET stripe_session_id = ?, updated_at = ? WHERE order_no = ?",
            (session_id, datetime.now(timezone.utc).isoformat(), order_no),
        )


def fail_order(order_no: str, reason: str = "") -> bool:
    """把仍处于 pending 的订单标记为 failed。

    用于 create-checkout 创建 Stripe 会话失败时回滚：否则会残留一条永远不会有
    webhook 回调的孤儿 pending 订单（用户订单列表里出现无法支付也无法关闭的记录）。
    仅翻转 pending，避免覆盖已支付订单（极端并发下 webhook 先到）。
    reason 写入 fail_reason 列，便于排查孤儿订单的失败原因。
    """
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE orders SET status = 'failed', fail_reason = ?, updated_at = ? "
            "WHERE order_no = ? AND status = 'pending'",
            ((reason or "")[:500], datetime.now(timezone.utc).isoformat(), order_no),
        )
        return cur.rowcount > 0


def complete_order(session_id: str, payment_intent_id: str) -> dict | None:
    """
    支付完成时更新订单状态、激活 VIP。
    并发安全：先用带 status='pending' 守卫的原子 UPDATE 占位，rowcount==0 说明
    已被并发/重复的 webhook 处理（或本就不是 pending），直接返回 None，避免重复
    续期导致 VIP 被翻倍延长。
    """
    return _complete_order_by(
        "stripe_session_id = ? AND status = 'pending'",
        (session_id,),
        session_id,
        payment_intent_id,
    )


def complete_order_by_order_no(
    order_no: str, session_id: str, payment_intent_id: str
) -> dict | None:
    """按订单号完成订单（complete_order 的 order_no 兜底路径）。

    场景：create-checkout 写库失败导致 stripe_session_id 未绑定到订单，
    webhook 按 session_id 匹配不到订单 → 用户已付款但 VIP 永不激活。
    此处按唯一订单号定位订单，并顺带补写 stripe_session_id。
    """
    return _complete_order_by(
        "order_no = ? AND status = 'pending'",
        (order_no,),
        session_id,
        payment_intent_id,
        extra_set="stripe_session_id = ?",
        extra_params=(session_id,),
    )


def _complete_order_by(
    where: str,
    where_params: tuple,
    session_id: str,
    payment_intent_id: str,
    extra_set: str = "",
    extra_params: tuple = (),
) -> dict | None:
    """订单置为 paid 并为用户续期的公共实现。

    where / where_params 决定如何定位待支付订单；extra_set 用于同时补写其他列。
    """
    from dateutil.relativedelta import relativedelta

    with get_db() as conn:
        now = datetime.now(timezone.utc).isoformat()
        sets = ["status = 'paid'", "stripe_payment_intent_id = ?", "paid_at = ?", "updated_at = ?"]
        params = [payment_intent_id, now, now]
        if extra_set:
            sets.append(extra_set)
            params.extend(extra_params)
        # 原子占位：仅把 pending 翻成 paid；并发下只有一个事务能命中（rowcount==1）。
        cur = conn.execute(
            f"UPDATE orders SET {', '.join(sets)} WHERE {where}",
            (*params, *where_params),
        )
        if cur.rowcount == 0:
            return None  # 已被并发/重复 webhook 处理，或订单非 pending

        # 只有赢家才续期；此刻 user 的 vip_expire_at 已是稳定快照（不存在其他赢家）。
        order = conn.execute(
            "SELECT * FROM orders WHERE stripe_session_id = ? AND status = 'paid'",
            (session_id,),
        ).fetchone()
        if order is None:
            return None
        user = conn.execute("SELECT * FROM users WHERE id = ?", (order["user_id"],)).fetchone()

        current_expire = None
        if user["vip_expire_at"]:
            try:
                s = user["vip_expire_at"]
                # 与 check_and_increment_summary 的时区处理保持一致：缺时区则按 UTC 补全，
                # 否则 naive 值与带时区的 base_time 比较会抛 TypeError。
                if "+" in s or "Z" in s:
                    current_expire = datetime.fromisoformat(s.replace("Z", "+00:00"))
                else:
                    current_expire = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        base_time = datetime.now(timezone.utc)
        if current_expire and current_expire > base_time:
            base_time = current_expire

        if order["plan_type"] == "monthly":
            new_expire = base_time + relativedelta(months=1)
        elif order["plan_type"] == "yearly":
            new_expire = base_time + relativedelta(years=1)
        else:
            new_expire = base_time + relativedelta(months=1)

        conn.execute(
            "UPDATE users SET is_vip = 1, vip_expire_at = ?, updated_at = ? WHERE id = ?",
            (new_expire.isoformat(), now, order["user_id"]),
        )

        return dict(order)  # 返回已更新为 paid 的订单（修复旧值返回 pending 的问题）


def get_order_by_no(order_no: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_no = ?", (order_no,)).fetchone()
        return dict(row) if row else None


def get_user_orders(user_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
