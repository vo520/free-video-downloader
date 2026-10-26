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
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
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
            CREATE INDEX IF NOT EXISTS idx_history_user_type_url ON history(user_id, type, video_url);
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
                key = (r["user_id"], r["type"], _normalize_video_url(r["video_url"]))
                groups.setdefault(key, []).append(r["id"])
            delete_ids = []
            for ids in groups.values():
                if len(ids) > 1:
                    delete_ids.extend(sorted(ids, reverse=True)[1:])  # 保留最大 id
            if delete_ids:
                placeholders = ",".join("?" * len(delete_ids))
                conn.execute(f"DELETE FROM history WHERE id IN ({placeholders})", delete_ids)
            for r in rows:
                norm = _normalize_video_url(r["video_url"])
                if norm != r["video_url"]:
                    conn.execute("UPDATE history SET video_url=? WHERE id=?", (norm, r["id"]))
            conn.execute("DROP INDEX IF EXISTS idx_history_user_type_url")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uniq_history_user_type_url "
                "ON history(user_id, type, video_url)"
            )
        except Exception as e:
            logging.warning("history 去重迁移跳过: %s", e)


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
    video_url = _normalize_video_url(video_url)
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


def get_history(user_id, htype=None, limit=50, offset=0):
    """读取当前用户的历史记录，按时间倒序。返回 (rows, total)。"""
    if not user_id:
        return [], 0
    with get_db() as conn:
        clauses = ["user_id = ?"]
        params = [user_id]
        if htype:
            clauses.append("type = ?")
            params.append(htype)
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
    """清空当前用户全部历史。"""
    if not user_id:
        return False
    with get_db() as conn:
        conn.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        return True


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

        if user["is_vip"] and user["vip_expire_at"]:
            try:
                expire_str = user["vip_expire_at"]
                if "+" in expire_str or "Z" in expire_str:
                    expire = datetime.fromisoformat(expire_str.replace("Z", "+00:00"))
                else:
                    expire = datetime.fromisoformat(expire_str).replace(tzinfo=timezone.utc)
                if expire > datetime.now(timezone.utc):
                    return True, -1  # -1 means unlimited
            except ValueError:
                pass

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

    并发安全：跨天重置与 +1 均通过带条件的 UPDATE（依赖 rowcount 判断），
    避免「先 SELECT 再 UPDATE」在并发下被突破日额度的问题。
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return False, 0

        if user["is_vip"] and user["vip_expire_at"]:
            try:
                expire_str = user["vip_expire_at"]
                if "+" in expire_str or "Z" in expire_str:
                    expire = datetime.fromisoformat(expire_str.replace("Z", "+00:00"))
                else:
                    expire = datetime.fromisoformat(expire_str).replace(tzinfo=timezone.utc)
                if expire > datetime.now(timezone.utc):
                    return True, -1  # -1 means unlimited
            except ValueError:
                pass

        # 跨天：直接清零并记为第 1 次。无条件更新即可（新用户 last_summary_date 为 NULL，
        # 带 `!= today` 的条件会因 NULL 比较失败而不生效）；并发两请求都置 1 不会超发。
        # 真正需要原子防超发的是下方同天 +1 分支（用 WHERE count < limit + rowcount 判定）。
        if user["last_summary_date"] != today:
            conn.execute(
                "UPDATE users SET daily_summary_count = 1, last_summary_date = ? WHERE id = ?",
                (today, user_id),
            )
            return True, FREE_DAILY_SUMMARY_LIMIT - 1

        # 同天内：仅当尚未达上限时才 +1，依赖 rowcount 判定是否成功（并发防超发）
        cur = conn.execute(
            "UPDATE users SET daily_summary_count = daily_summary_count + 1 "
            "WHERE id = ? AND daily_summary_count < ?",
            (user_id, FREE_DAILY_SUMMARY_LIMIT),
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
        conn.execute(
            "UPDATE orders SET stripe_session_id = ?, updated_at = datetime('now') WHERE order_no = ?",
            (session_id, order_no),
        )


def fail_order(order_no: str, reason: str = "") -> bool:
    """把仍处于 pending 的订单标记为 failed。

    用于 create-checkout 创建 Stripe 会话失败时回滚：否则会残留一条永远不会有
    webhook 回调的孤儿 pending 订单（用户订单列表里出现无法支付也无法关闭的记录）。
    仅翻转 pending，避免覆盖已支付订单（极端并发下 webhook 先到）。
    """
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE orders SET status = 'failed', updated_at = ? "
            "WHERE order_no = ? AND status = 'pending'",
            (datetime.now(timezone.utc).isoformat(), order_no),
        )
        return cur.rowcount > 0


def complete_order(session_id: str, payment_intent_id: str) -> dict | None:
    """
    支付完成时更新订单状态、激活 VIP。
    并发安全：先用带 status='pending' 守卫的原子 UPDATE 占位，rowcount==0 说明
    已被并发/重复的 webhook 处理（或本就不是 pending），直接返回 None，避免重复
    续期导致 VIP 被翻倍延长。
    """
    from dateutil.relativedelta import relativedelta

    with get_db() as conn:
        now = datetime.now(timezone.utc).isoformat()
        # 原子占位：仅把 pending 翻成 paid；并发下只有一个事务能命中（rowcount==1）。
        cur = conn.execute(
            "UPDATE orders SET status = 'paid', stripe_payment_intent_id = ?, "
            "paid_at = ?, updated_at = ? WHERE stripe_session_id = ? AND status = 'pending'",
            (payment_intent_id, now, now, session_id),
        )
        if cur.rowcount == 0:
            return None  # 已被并发/重复 webhook 处理，或订单非 pending

        # 只有赢家才续期；此刻 user 的 vip_expire_at 已是稳定快照（不存在其他赢家）。
        order = conn.execute(
            "SELECT * FROM orders WHERE stripe_session_id = ? AND status = 'paid'",
            (session_id,),
        ).fetchone()
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
