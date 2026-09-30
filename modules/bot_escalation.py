"""Official bot escalation – @AbuseNotification, @SearchReport, @NoToScam."""
import asyncio
import random
from typing import List, Dict, Any

from telethon.errors import FloodWaitError

import config
from utils.logger import log
from utils.helpers import human_delay, random_ref_id
from modules.account_pool import Account


class BotEscalation:
    def __init__(self):
        self.messaged = 0

    def _abuse_message(self, evidence: Dict[str, Any], target: str) -> str:
        links = "\n".join(evidence.get("sample_links", [])[:6])
        excerpts = " | ".join(evidence.get("excerpts", [])[:3])
        return (
            f"ABUSE REPORT – REF {random_ref_id()}\n"
            f"Target: @{evidence.get('username', target.lstrip('@'))}\n"
            f"Type: {evidence.get('entity_type', 'channel')}\n"
            f"Link: {evidence.get('link')}\n"
            f"Violations: spam / scam / ToS / potential illegal content\n"
            f"Evidence links:\n{links}\n"
            f"Sample: {excerpts[:200]}\n"
            f"Date range: {evidence.get('date_range', 'n/a')}\n"
            f"Request: permanent restriction / content removal.\n"
            f"Submitted in good faith under Telegram ToS."
        )

    def _search_message(self, target: str, evidence: Dict[str, Any]) -> str:
        uname = evidence.get("username", target.lstrip("@"))
        return (
            f"Search surface request – REF {random_ref_id()}\n"
            f"Terms that lead to violating content: {uname}, "
            f"{evidence.get('title', '')}\n"
            f"Channel: https://t.me/{uname}\n"
            f"Please review ranking / visibility of this target."
        )

    def _scam_message(self, evidence: Dict[str, Any], target: str) -> str:
        return (
            f"SCAM / IMPERSONATION REPORT – REF {random_ref_id()}\n"
            f"Target: @{evidence.get('username', target.lstrip('@'))}\n"
            f"Link: {evidence.get('link')}\n"
            f"Indicators: fraud patterns, misleading claims in posts.\n"
            f"Sample IDs: {evidence.get('sample_ids', [])[:5]}\n"
            f"Request: ban / restrict."
        )

    async def _send(self, account: Account, bot_username: str, text: str) -> bool:
        client = account.client
        if not client:
            return False
        try:
            await client.send_message(bot_username, text[:4000])
            self.messaged += 1
            log.info(f"[{account.phone}] → @{bot_username} OK")
            return True
        except FloodWaitError as e:
            log.warning(f"[{account.phone}] bot FloodWait {e.seconds}s")
            await asyncio.sleep(e.seconds + 1)
            return False
        except Exception as e:
            log.error(f"[{account.phone}] bot @{bot_username} fail: {e}")
            return False

    async def run(self, accounts: List[Account], target: str, evidence: Dict[str, Any]):
        if not accounts:
            log.warning("No accounts for bot escalation")
            return 0
        shuffled = accounts.copy()
        random.shuffle(shuffled)
        bots = [
            (config.ABUSE_BOT, self._abuse_message(evidence, target)),
            (config.SEARCH_REPORT_BOT, self._search_message(target, evidence)),
            (config.NOTOSCAM_BOT, self._scam_message(evidence, target)),
        ]
        idx = 0
        for bot, text in bots:
            acc = shuffled[idx % len(shuffled)]
            idx += 1
            await self._send(acc, bot, text)
            await human_delay(3.0, 8.0)
        log.info(f"Bot escalation done → {self.messaged} messages")
        return self.messaged
