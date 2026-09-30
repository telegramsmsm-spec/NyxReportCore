"""Live proxy harvester – scrape operator-supplied channels, test, keep clean ones."""
import asyncio
import re
from typing import List, Optional, Set

from telethon import TelegramClient
from telethon.tl.types import Message
import aiohttp

import config
from utils.logger import log
from utils.db import StateDB
from utils.helpers import extract_proxies_from_text, parse_proxy_line, human_delay


class ProxyHarvester:
    def __init__(self, client: TelegramClient, db: StateDB, channels: List[str]):
        self.client = client
        self.db = db
        self.channels = [c.lstrip("@") for c in channels]
        self._seen: Set[str] = set()
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self.alive_count = 0

    async def _test_socks_http(self, proxy: dict) -> bool:
        try:
            from aiohttp_socks import ProxyConnector
            url = f"{proxy['proto']}://"
            if proxy.get("user"):
                url += f"{proxy['user']}:{proxy.get('password','')}@"
            url += f"{proxy['host']}:{proxy['port']}"
            connector = ProxyConnector.from_url(url)
            timeout = aiohttp.ClientTimeout(total=config.PROXY_TEST_TIMEOUT)
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as sess:
                async with sess.get("https://api.telegram.org") as resp:
                    return resp.status < 500
        except ImportError:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(proxy["host"], proxy["port"]),
                    timeout=config.PROXY_TEST_TIMEOUT,
                )
                writer.close()
                await writer.wait_closed()
                return True
            except Exception:
                return False
        except Exception:
            return False

    async def test_proxy(self, proxy: dict) -> bool:
        if proxy.get("proto") == "mtproto":
            return True
        return await self._test_socks_http(proxy)

    async def ingest(self, text: str):
        proxies = extract_proxies_from_text(text)
        for p in proxies:
            raw = p["raw"]
            if raw in self._seen:
                continue
            self._seen.add(raw)
            ok = await self.test_proxy(p)
            if ok:
                await self.db.upsert_proxy(raw, p["proto"], alive=True)
                self.alive_count += 1
                log.info(f"Proxy OK → {raw}")
            else:
                await self.db.upsert_proxy(raw, p["proto"], alive=False)
                log.debug(f"Proxy dead → {raw}")

    async def scrape_channel(self, username: str, limit: int = 40):
        try:
            entity = await self.client.get_entity(username)
            messages = await self.client.get_messages(entity, limit=limit)
            for msg in messages:
                if isinstance(msg, Message) and msg.message:
                    await self.ingest(msg.message)
        except Exception as e:
            log.warning(f"Proxy channel @{username} scrape fail: {e}")

    async def _loop(self):
        log.info(f"Proxy harvester watching: {self.channels}")
        while not self._stop.is_set():
            for ch in self.channels:
                if self._stop.is_set():
                    break
                await self.scrape_channel(ch)
                await human_delay(1.0, 3.0)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=config.PROXY_REFRESH_SECONDS)
                break
            except asyncio.TimeoutError:
                pass

    def start(self):
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info(f"Proxy harvester stopped (alive tracked: {self.alive_count})")

    async def load_seed_file(self, path=config.PROXIES_FILE):
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                p = parse_proxy_line(line)
                if p:
                    ok = await self.test_proxy(p)
                    await self.db.upsert_proxy(p["raw"], p["proto"], alive=ok)
                    if ok:
                        self._seen.add(p["raw"])
                        self.alive_count += 1
        log.info(f"Seed proxies loaded, alive≈{self.alive_count}")
