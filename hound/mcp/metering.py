"""Persistent API-key management and usage metering (SQLite).

Env:
  HOUND_ADMIN_KEY       - bearer key for /admin/* endpoints
  HOUND_METER_DB        - sqlite path (default hound-meter.db)
  HOUND_DEFAULT_RPM     - per-key requests/min (default 60)
  HOUND_DEFAULT_DAILY   - per-key requests/day (default 2000)
  HOUND_DEFAULT_TOKENS  - per-key token quota/day (0 = unlimited)
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _db_path() -> Path:
    return Path(os.environ.get("HOUND_METER_DB", "hound-meter.db")).expanduser()


@dataclass
class KeyInfo:
    key: str
    name: str
    active: bool
    rpm: int
    daily: int
    token_daily: int


class MeterStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or _db_path()
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()
        self._bootstrap_env_keys()

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    key TEXT PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    rpm INTEGER NOT NULL DEFAULT 60,
                    daily INTEGER NOT NULL DEFAULT 2000,
                    token_daily INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    ts REAL NOT NULL,
                    path TEXT NOT NULL,
                    tokens INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_usage_key_ts ON usage(key, ts);
                """
            )
            self._conn.commit()

    def _bootstrap_env_keys(self) -> None:
        # migrate env keys into DB as active keys (idempotent)
        raw = []
        k = os.environ.get("HOUND_API_KEY", "").strip()
        if k:
            raw.append(k)
        for part in os.environ.get("HOUND_API_KEYS", "").split(","):
            part = part.strip()
            if part:
                raw.append(part)
        for i, key in enumerate(raw):
            self.upsert_key(key, name=f"env-{i+1}")

    def upsert_key(self, key: str, name: str = "", active: bool = True, rpm: Optional[int] = None,
                   daily: Optional[int] = None, token_daily: Optional[int] = None) -> None:
        rpm = int(os.environ.get("HOUND_DEFAULT_RPM", "60")) if rpm is None else rpm
        daily = int(os.environ.get("HOUND_DEFAULT_DAILY", "2000")) if daily is None else daily
        token_daily = int(os.environ.get("HOUND_DEFAULT_TOKENS", "0")) if token_daily is None else token_daily
        with self._lock:
            self._conn.execute(
                """INSERT INTO api_keys(key,name,active,rpm,daily,token_daily,created_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(key) DO UPDATE SET name=excluded.name, active=excluded.active,
                     rpm=excluded.rpm, daily=excluded.daily, token_daily=excluded.token_daily""",
                (key, name, 1 if active else 0, rpm, daily, token_daily, time.time()),
            )
            self._conn.commit()

    def create_key(self, name: str = "", **limits) -> str:
        key = "hk_" + secrets.token_urlsafe(24)
        self.upsert_key(key, name=name, **limits)
        return key

    def revoke_key(self, key: str) -> bool:
        with self._lock:
            cur = self._conn.execute("UPDATE api_keys SET active=0 WHERE key=?", (key,))
            self._conn.commit()
            return cur.rowcount > 0

    def list_keys(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT key,name,active,rpm,daily,token_daily,created_at FROM api_keys ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_key(self, key: str) -> Optional[KeyInfo]:
        with self._lock:
            r = self._conn.execute(
                "SELECT key,name,active,rpm,daily,token_daily FROM api_keys WHERE key=?", (key,)
            ).fetchone()
        if not r:
            return None
        return KeyInfo(**dict(r))

    def auth_required(self) -> bool:
        # require auth if any active key exists or env/admin configured
        with self._lock:
            r = self._conn.execute("SELECT 1 FROM api_keys WHERE active=1 LIMIT 1").fetchone()
        return bool(r) or bool(os.environ.get("HOUND_ADMIN_KEY"))

    def check_and_record(self, key: str, path: str, tokens: int = 0) -> tuple[bool, str]:
        info = self.get_key(key)
        if not info or not info.active:
            return False, "invalid_key"
        now = time.time()
        min_ago = now - 60
        day_ago = now - 86400
        with self._lock:
            rpm_n = self._conn.execute(
                "SELECT COUNT(*) c FROM usage WHERE key=? AND ts>=?", (key, min_ago)
            ).fetchone()["c"]
            if info.rpm > 0 and rpm_n >= info.rpm:
                return False, "rate_limited_rpm"
            day_n = self._conn.execute(
                "SELECT COUNT(*) c FROM usage WHERE key=? AND ts>=?", (key, day_ago)
            ).fetchone()["c"]
            if info.daily > 0 and day_n >= info.daily:
                return False, "quota_exceeded_daily"
            if info.token_daily > 0:
                tok = self._conn.execute(
                    "SELECT COALESCE(SUM(tokens),0) s FROM usage WHERE key=? AND ts>=?", (key, day_ago)
                ).fetchone()["s"]
                if tok + max(tokens, 0) > info.token_daily:
                    return False, "token_quota_exceeded"
            self._conn.execute(
                "INSERT INTO usage(key,ts,path,tokens) VALUES(?,?,?,?)",
                (key, now, path, max(int(tokens), 0)),
            )
            self._conn.commit()
        return True, "ok"

    def usage_summary(self, key: Optional[str] = None):
        now = time.time()
        day_ago = now - 86400
        q = "SELECT key, COUNT(*) requests, COALESCE(SUM(tokens),0) tokens FROM usage WHERE ts>=?"
        args = [day_ago]
        if key:
            q += " AND key=?"
            args.append(key)
        q += " GROUP BY key"
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        with self._lock:
            self._conn.close()
