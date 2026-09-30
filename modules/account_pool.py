"""Account pool – load, health-check, quarantine, keep-alive, sticky proxy."""
import asyncio
import json
import random
from pathlib import Path
from typing import List, Optional, Dict, Any

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    AuthKeyUnregisteredError, UserDeactivatedBanError, UserDeactivatedError,
    SessionPasswordNeededError, FloodWaitError, RPCError,
)

import config
from utils.logger import log
from utils.db import StateDB
from utils.helpers import random_device, human_delay, proxy_to_telethon, parse_proxy_line


class Account:
    def __init__(self, data: Dict[str, Any]):
        self.phone = str(data.get("phone", ""))
        self.api_id = int(data["api_id"])
        self.api_hash = str(data["api_hash"])
        self.session_name = data.get("session_name") or f"sess_{self.phone[-4:]}"
        self.string_session = data.get("string_session")
        self.twofa = data.get("2fa") or data.get("twofa")
        self.proxy_raw = data.get("proxy")
        self.proxy_dict: Optional[Dict] = None
        self.client: Optional[TelegramClient] = None
        self.status = "unknown"
        self.reports_this_wave = 0
        self._device = random_device()

    def _build_proxy(self):
        if self.proxy_raw:
            self.proxy_dict = parse_proxy_line(self.proxy_raw) if isinstance(self.proxy_raw, str) else self.proxy_raw
        return proxy_to_telethon(self.proxy_dict) if self.proxy_dict else None

    def create_client(self) -> TelegramClient:
        proxy = self._build_proxy()
        session = StringSession(self.string_session) if self.string_session else self.session_name
        kwargs = dict(
            device_model=self._device["device_model"],
            system_version=self._device["system_version"],
            app_version=self._device["app_version"],
            lang_code=self._device["lang_code"],
            system_lang_code=self._device["system_lang_code"],
        )
        if proxy:
            kwargs["proxy"] = proxy
        client = TelegramClient(session, self.api_id, self.api_hash, **kwargs)
        self.client = client
        return client

    async def connect_and_check(self, db: StateDB) -> bool:
        try:
            client = self.create_client()
            await asyncio.wait_for(client.connect(), timeout=config.ACCOUNT_HEALTH_TIMEOUT)
            if not await client.is_user_authorized():
                log.warning(f"[{self.phone}] not authorized – quarantine")
                self.status = "unauthorized"
                await db.upsert_account(self.phone, self.session_name, self.status, self.proxy_raw, "not authorized")
                await client.disconnect()
                return False
            me = await client.get_me()
            self.status = "alive"
            await db.upsert_account(self.phone, self.session_name, "alive", self.proxy_raw)
            log.info(f"[{self.phone}] alive as @{getattr(me, 'username', me.id)}")
            return True
        except (AuthKeyUnregisteredError, UserDeactivatedBanError, UserDeactivatedError) as e:
            self.status = "banned"
            await db.upsert_account(self.phone, self.session_name, "banned", self.proxy_raw, str(e))
            log.error(f"[{self.phone}] banned/dead: {e}")
            if self.client:
                await self.client.disconnect()
            return False
        except FloodWaitError as e:
            self.status = "flood"
            await db.upsert_account(self.phone, self.session_name, "flood", self.proxy_raw, f"FloodWait {e.seconds}s")
            log.warning(f"[{self.phone}] FloodWait {e.seconds}s")
            return False
        except asyncio.TimeoutError:
            self.status = "timeout"
            await db.upsert_account(self.phone, self.session_name, "timeout", self.proxy_raw, "connect timeout")
            log.warning(f"[{self.phone}] connect timeout")
            return False
        except Exception as e:
            self.status = "error"
            await db.upsert_account(self.phone, self.session_name, "error", self.proxy_raw, str(e)[:200])
            log.error(f"[{self.phone}] health error: {e}")
            if self.client:
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
            return False

    async def keep_alive(self):
        if not self.client or not self.client.is_connected():
            return
        try:
            await self.client.get_me()
        except Exception as e:
            log.debug(f"[{self.phone}] keep-alive fail: {e}")

    async def disconnect(self):
        if self.client:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.client = None


class AccountPool:
    def __init__(self, db: StateDB):
        self.db = db
        self.accounts: List[Account] = []
        self._keepalive_task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    def load_from_file(self, path: Path = config.ACCOUNTS_FILE):
        if not path.exists():
            log.error(f"accounts file missing: {path}")
            return
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self.accounts = [Account(a) for a in raw]
        log.info(f"Loaded {len(self.accounts)} accounts from {path}")

    async def health_check_all(self):
        log.info("Running account health checks…")
        sem = asyncio.Semaphore(5)

        async def _one(acc: Account):
            async with sem:
                await acc.connect_and_check(self.db)

        await asyncio.gather(*[_one(a) for a in self.accounts])
        alive = [a for a in self.accounts if a.status == "alive"]
        log.info(f"Health done → {len(alive)}/{len(self.accounts)} alive")
        return alive

    def get_alive(self) -> List[Account]:
        return [a for a in self.accounts if a.status == "alive" and a.client]

    def assign_proxy(self, account: Account, proxy_raw: str):
        account.proxy_raw = proxy_raw
        account.proxy_dict = parse_proxy_line(proxy_raw)
        log.info(f"[{account.phone}] sticky proxy assigned")

    async def _keepalive_loop(self):
        while not self._stop.is_set():
            wait = random.uniform(config.SESSION_KEEPALIVE_MIN * 60, config.SESSION_KEEPALIVE_MAX * 60)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=wait)
                break
            except asyncio.TimeoutError:
                pass
            for acc in self.get_alive():
                await acc.keep_alive()
                await human_delay(0.5, 1.5)

    def start_keepalive(self):
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        log.info("Session keep-alive started")

    async def stop(self):
        self._stop.set()
        if self._keepalive_task:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
        for acc in self.accounts:
            await acc.disconnect()
        log.info("Account pool stopped")
