"""SQLite state store – accounts health, proxies, campaign stats."""
import aiosqlite
from pathlib import Path
from typing import Optional, List, Dict, Any

import config
from utils.logger import log


SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    phone TEXT PRIMARY KEY,
    session_name TEXT,
    status TEXT DEFAULT 'unknown',
    last_check TEXT,
    reports_sent INTEGER DEFAULT 0,
    quarantine_reason TEXT,
    proxy TEXT
);

CREATE TABLE IF NOT EXISTS proxies (
    proxy TEXT PRIMARY KEY,
    proto TEXT,
    last_ok TEXT,
    fails INTEGER DEFAULT 0,
    assigned_to TEXT,
    is_alive INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target TEXT,
    started_at TEXT,
    finished_at TEXT,
    reports_ok INTEGER DEFAULT 0,
    reports_fail INTEGER DEFAULT 0,
    emails_sent INTEGER DEFAULT 0,
    bots_messaged INTEGER DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS report_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER,
    account TEXT,
    target TEXT,
    reason TEXT,
    success INTEGER,
    detail TEXT,
    ts TEXT
);
"""


class StateDB:
    def __init__(self, path: Path = config.DB_PATH):
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        log.info(f"State DB ready → {self.path}")

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def upsert_account(self, phone: str, session_name: str, status: str,
                             proxy: Optional[str] = None, reason: str = ""):
        await self._conn.execute(
            """INSERT INTO accounts (phone, session_name, status, last_check, proxy, quarantine_reason)
               VALUES (?, ?, ?, datetime('now'), ?, ?)
               ON CONFLICT(phone) DO UPDATE SET
                 status=excluded.status,
                 last_check=datetime('now'),
                 proxy=COALESCE(excluded.proxy, accounts.proxy),
                 quarantine_reason=excluded.quarantine_reason
            """,
            (phone, session_name, status, proxy, reason),
        )
        await self._conn.commit()

    async def increment_reports(self, phone: str, n: int = 1):
        await self._conn.execute(
            "UPDATE accounts SET reports_sent = reports_sent + ? WHERE phone = ?",
            (n, phone),
        )
        await self._conn.commit()

    async def get_alive_accounts(self) -> List[Dict[str, Any]]:
        cur = await self._conn.execute(
            "SELECT * FROM accounts WHERE status = 'alive'"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def upsert_proxy(self, proxy: str, proto: str, alive: bool = True,
                           assigned: Optional[str] = None):
        await self._conn.execute(
            """INSERT INTO proxies (proxy, proto, last_ok, fails, assigned_to, is_alive)
               VALUES (?, ?, datetime('now'), 0, ?, ?)
               ON CONFLICT(proxy) DO UPDATE SET
                 last_ok=CASE WHEN ? THEN datetime('now') ELSE proxies.last_ok END,
                 fails=CASE WHEN ? THEN 0 ELSE proxies.fails + 1 END,
                 is_alive=?,
                 assigned_to=COALESCE(?, proxies.assigned_to)
            """,
            (proxy, proto, assigned, 1 if alive else 0,
             alive, alive, 1 if alive else 0, assigned),
        )
        await self._conn.commit()

    async def drop_proxy(self, proxy: str):
        await self._conn.execute("UPDATE proxies SET is_alive=0 WHERE proxy=?", (proxy,))
        await self._conn.commit()

    async def get_free_proxies(self, limit: int = 50) -> List[str]:
        cur = await self._conn.execute(
            "SELECT proxy FROM proxies WHERE is_alive=1 AND (assigned_to IS NULL OR assigned_to='') LIMIT ?",
            (limit,),
        )
        rows = await cur.fetchall()
        return [r[0] for r in rows]

    async def assign_proxy(self, proxy: str, phone: str):
        await self._conn.execute(
            "UPDATE proxies SET assigned_to=? WHERE proxy=?", (phone, proxy)
        )
        await self._conn.commit()

    async def start_campaign(self, target: str) -> int:
        cur = await self._conn.execute(
            "INSERT INTO campaigns (target, started_at) VALUES (?, datetime('now'))",
            (target,),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def finish_campaign(self, cid: int, reports_ok: int, reports_fail: int,
                              emails: int, bots: int, notes: str = ""):
        await self._conn.execute(
            """UPDATE campaigns SET finished_at=datetime('now'),
               reports_ok=?, reports_fail=?, emails_sent=?, bots_messaged=?, notes=?
               WHERE id=?""",
            (reports_ok, reports_fail, emails, bots, notes, cid),
        )
        await self._conn.commit()

    async def log_report(self, cid: int, account: str, target: str,
                         reason: str, success: bool, detail: str):
        await self._conn.execute(
            """INSERT INTO report_log (campaign_id, account, target, reason, success, detail, ts)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            (cid, account, target, reason, 1 if success else 0, detail),
        )
        await self._conn.commit()
