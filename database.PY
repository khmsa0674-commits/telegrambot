"""
╔══════════════════════════════════════════════╗
║      🗄️  Database Manager - VideoBot        ║
╚══════════════════════════════════════════════╝
"""

import sqlite3
import logging
from datetime import datetime, date
from contextlib import contextmanager
from config import DATABASE_PATH

logger = logging.getLogger(__name__)


@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database tables"""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                last_name   TEXT,
                is_banned   INTEGER DEFAULT 0,
                is_premium  INTEGER DEFAULT 0,
                joined_at   TEXT DEFAULT (datetime('now')),
                last_seen   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS downloads (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                platform    TEXT NOT NULL,
                url         TEXT NOT NULL,
                status      TEXT NOT NULL,   -- success / failed
                downloaded_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS channels (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id  TEXT NOT NULL UNIQUE,
                title       TEXT,
                is_active   INTEGER DEFAULT 1,
                added_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS broadcasts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id    INTEGER NOT NULL,
                message     TEXT NOT NULL,
                sent_to     INTEGER DEFAULT 0,
                failed      INTEGER DEFAULT 0,
                sent_at     TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_downloads_user ON downloads(user_id);
            CREATE INDEX IF NOT EXISTS idx_downloads_date ON downloads(downloaded_at);
        """)
    logger.info("✅ Database initialized successfully")


# ─── Users ─────────────────────────────────────────────────────────────────────

def upsert_user(user_id: int, username: str = None,
                first_name: str = None, last_name: str = None):
    """Add or update user record"""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, last_seen)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name,
                last_name  = excluded.last_name,
                last_seen  = datetime('now')
        """, (user_id, username, first_name, last_name))


def get_user(user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_users(include_banned: bool = False) -> list[int]:
    with get_db() as conn:
        q = "SELECT user_id FROM users"
        if not include_banned:
            q += " WHERE is_banned = 0"
        rows = conn.execute(q).fetchall()
        return [r["user_id"] for r in rows]


def get_users_count() -> dict:
    with get_db() as conn:
        total   = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active  = conn.execute("SELECT COUNT(*) FROM users WHERE is_banned = 0").fetchone()[0]
        premium = conn.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1").fetchone()[0]
        today   = conn.execute(
            "SELECT COUNT(*) FROM users WHERE DATE(joined_at) = DATE('now')"
        ).fetchone()[0]
        return {"total": total, "active": active, "premium": premium, "today": today}


def ban_user(user_id: int, ban: bool = True):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET is_banned = ? WHERE user_id = ?",
            (1 if ban else 0, user_id)
        )


def set_premium(user_id: int, premium: bool = True):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET is_premium = ? WHERE user_id = ?",
            (1 if premium else 0, user_id)
        )


def is_banned(user_id: int) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT is_banned FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return bool(row["is_banned"]) if row else False


def is_premium(user_id: int) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT is_premium FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return bool(row["is_premium"]) if row else False


# ─── Downloads ────────────────────────────────────────────────────────────────

def log_download(user_id: int, platform: str, url: str, status: str = "success"):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO downloads (user_id, platform, url, status)
            VALUES (?, ?, ?, ?)
        """, (user_id, platform, url, status))


def get_today_downloads(user_id: int) -> int:
    with get_db() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM downloads
            WHERE user_id = ? AND DATE(downloaded_at) = DATE('now') AND status = 'success'
        """, (user_id,)).fetchone()
        return row["cnt"]


def get_download_stats() -> dict:
    with get_db() as conn:
        total   = conn.execute("SELECT COUNT(*) FROM downloads WHERE status='success'").fetchone()[0]
        today   = conn.execute(
            "SELECT COUNT(*) FROM downloads WHERE status='success' AND DATE(downloaded_at)=DATE('now')"
        ).fetchone()[0]
        by_plat = conn.execute("""
            SELECT platform, COUNT(*) as cnt FROM downloads
            WHERE status='success' GROUP BY platform ORDER BY cnt DESC
        """).fetchall()
        return {
            "total": total,
            "today": today,
            "by_platform": {r["platform"]: r["cnt"] for r in by_plat},
        }


# ─── Channels ─────────────────────────────────────────────────────────────────

def add_channel(channel_id: str, title: str = None):
    with get_db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO channels (channel_id, title, is_active)
            VALUES (?, ?, 1)
        """, (channel_id, title))


def remove_channel(channel_id: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE channels SET is_active = 0 WHERE channel_id = ?",
            (channel_id,)
        )


def get_active_channels() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM channels WHERE is_active = 1"
        ).fetchall()
        return [dict(r) for r in rows]


# ─── Broadcasts ───────────────────────────────────────────────────────────────

def log_broadcast(admin_id: int, message: str, sent_to: int, failed: int):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO broadcasts (admin_id, message, sent_to, failed)
            VALUES (?, ?, ?, ?)
        """, (admin_id, message, sent_to, failed))


def get_broadcast_history(limit: int = 5) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM broadcasts ORDER BY sent_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
