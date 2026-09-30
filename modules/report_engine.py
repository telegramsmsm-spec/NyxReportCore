"""Inside-Telegram multi-account report engine."""
import asyncio
import random
from typing import List, Dict, Any, Optional

from telethon import TelegramClient
from telethon.tl.functions.messages import ReportRequest, ReportSpamRequest
from telethon.tl.functions.account import ReportPeerRequest
from telethon.tl.types import (
    InputReportReasonChildAbuse, InputReportReasonSpam,
    InputReportReasonViolence, InputReportReasonPornography,
    InputReportReasonCopyright, InputReportReasonOther,
    InputReportReasonFake, InputPeerChannel, InputPeerUser, InputPeerChat,
)
from telethon.errors import FloodWaitError, RPCError, ChatAdminRequiredError

import config
from utils.logger import log
from utils.db import StateDB
from utils.helpers import human_delay, weighted_reason, unique_report_comment
from modules.account_pool import Account


REASON_MAP = {
    "child_abuse": InputReportReasonChildAbuse(),
    "spam": InputReportReasonSpam(),
    "violence": InputReportReasonViolence(),
    "pornography": InputReportReasonPornography(),
    "copyright": InputReportReasonCopyright(),
    "scam": InputReportReasonFake(),
    "other": InputReportReasonOther(),
}


class ReportEngine:
    def __init__(self, db: StateDB, campaign_id: int):
        self.db = db
        self.campaign_id = campaign_id
        self.success = 0
        self.fail = 0
        self._pause = asyncio.Event()
        self._pause.set()
        self._flood_lock = asyncio.Lock()

    async def _global_flood_pause(self, seconds: int):
        async with self._flood_lock:
            if not self._pause.is_set():
                return
            self._pause.clear()
            log.warning(f"Mass FloodWait – global pause {seconds}s")
            await asyncio.sleep(min(seconds, config.FLOODWAIT_PAUSE_GLOBAL))
            self._pause.set()

    async def report_peer(self, account: Account, target: str, evidence: Dict[str, Any],
                          reason: Optional[str] = None) -> bool:
        await self._pause.wait()
        client = account.client
        if not client:
            return False
        reason = reason or weighted_reason()
        comment = unique_report_comment(reason, evidence, target)
        tl_reason = REASON_MAP.get(reason, InputReportReasonOther())

        try:
            entity = await client.get_entity(target.lstrip("@"))
            msg_ids = evidence.get("sample_ids", [])[:5]
            if msg_ids:
                await client(ReportRequest(
                    peer=entity,
                    id=msg_ids,
                    reason=tl_reason,
                    message=comment[:200],
                ))
            else:
                await client(ReportPeerRequest(
                    peer=entity,
                    reason=tl_reason,
                    message=comment[:200],
                ))
            self.success += 1
            account.reports_this_wave += 1
            await self.db.increment_reports(account.phone)
            await self.db.log_report(
                self.campaign_id, account.phone, target, reason, True, comment[:80]
            )
            log.info(f"[{account.phone}] report OK reason={reason} → @{target.lstrip('@')}")
            return True
        except FloodWaitError as e:
            self.fail += 1
            await self.db.log_report(
                self.campaign_id, account.phone, target, reason, False, f"FloodWait {e.seconds}"
            )
            log.warning(f"[{account.phone}] FloodWait {e.seconds}s")
            if e.seconds > 30:
                await self._global_flood_pause(e.seconds)
            else:
                await asyncio.sleep(e.seconds + 1)
            return False
        except Exception as e:
            self.fail += 1
            await self.db.log_report(
                self.campaign_id, account.phone, target, reason, False, str(e)[:120]
            )
            log.error(f"[{account.phone}] report fail: {e}")
            return False

    async def run_wave(self, accounts: List[Account], target: str, evidence: Dict[str, Any],
                       reports_per_account: int = None):
        reports_per_account = reports_per_account or config.MAX_REPORTS_PER_ACCOUNT_WAVE
        workers = min(config.REPORT_WORKERS, len(accounts))
        log.info(f"Report wave: {len(accounts)} accounts, {workers} workers, "
                 f"max {reports_per_account}/acc → @{target.lstrip('@')}")

        queue: asyncio.Queue = asyncio.Queue()
        for acc in accounts:
            for _ in range(reports_per_account):
                await queue.put(acc)

        async def worker():
            while True:
                try:
                    acc = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if acc.reports_this_wave >= reports_per_account:
                    queue.task_done()
                    continue
                await self.report_peer(acc, target, evidence)
                await human_delay()
                queue.task_done()

        tasks = [asyncio.create_task(worker()) for _ in range(workers)]
        await asyncio.gather(*tasks)
        log.info(f"Wave finished → success={self.success} fail={self.fail}")
        return self.success, self.fail
