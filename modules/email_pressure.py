"""Outside email pressure layer – rotate SMTP + Telegram abuse mailboxes."""
import asyncio
import json
import random
from email.message import EmailMessage
from pathlib import Path
from typing import List, Dict, Any

import aiosmtplib

import config
from utils.logger import log, utc_now
from utils.helpers import human_delay, random_ref_id


SUBJECTS = [
    "URGENT ABUSE REPORT – @{target} – {vtype} – {ts}",
    "Child safety / illegal content report – @{target}",
    "Scam & fraud channel – permanent ban request – @{target}",
    "Copyright + ToS violation – @{target}",
    "Spam & mass ToS breach – @{target} – action required",
    "Trust & Safety escalation – @{target} – evidence attached in body",
]


class EmailPressure:
    def __init__(self):
        self.smtp_accounts: List[Dict] = []
        self.sent = 0
        self.failed = 0

    def load(self, path: Path = config.SMTP_FILE):
        if not path.exists():
            log.error(f"SMTP file missing: {path}")
            return
        with open(path, "r", encoding="utf-8") as f:
            self.smtp_accounts = json.load(f)
        log.info(f"Loaded {len(self.smtp_accounts)} SMTP accounts")

    def _build_body(self, evidence: Dict[str, Any], vtype: str) -> str:
        links = "\n".join(f"- {l}" for l in evidence.get("sample_links", [])[:10])
        ids = ", ".join(str(i) for i in evidence.get("sample_ids", [])[:15])
        excerpts = "\n".join(f'  "{e}"' for e in evidence.get("excerpts", [])[:5])
        ref = random_ref_id()
        return f"""Hello Telegram Abuse / Trust & Safety Team,

Target: @{evidence.get('username')} / {evidence.get('link')}
Type: {evidence.get('entity_type', 'Channel / Group')}
Title: {evidence.get('title', 'n/a')}
Primary violations: {vtype}

Evidence (auto-harvested):
- Direct links to specific posts:
{links or '  (see message IDs)'}
- Message IDs: {ids or 'n/a'}
- Sample content excerpts:
{excerpts or '  n/a'}
- Dates of activity: {evidence.get('date_range') or 'n/a'}
- Approximate views in sample: {evidence.get('total_views_sampled', 0)}
- Subscribers/participants: {evidence.get('participants') or 'n/a'}

Request: immediate permanent restriction / content removal / account ban.

Additional evidence available on request.
This report is submitted in good faith under Telegram Terms of Service and applicable law.

Reporter reference: {ref}
Timestamp: {utc_now()}

Best regards,
Compliance System
"""

    async def _send_one(self, smtp: Dict, to_addr: str, subject: str, body: str) -> bool:
        msg = EmailMessage()
        msg["From"] = f"{smtp.get('from_name', 'Reporter')} <{smtp['user']}>"
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            await aiosmtplib.send(
                msg,
                hostname=smtp["host"],
                port=int(smtp.get("port", 587)),
                username=smtp["user"],
                password=smtp["password"],
                start_tls=smtp.get("use_tls", True),
                timeout=config.SMTP_TIMEOUT,
            )
            self.sent += 1
            log.info(f"Email OK → {to_addr} via {smtp['user']}")
            return True
        except Exception as e:
            self.failed += 1
            log.error(f"Email fail → {to_addr} ({smtp['user']}): {e}")
            return False

    async def run(self, evidence: Dict[str, Any], volume: int = None):
        volume = volume or config.DEFAULT_EMAILS
        if not self.smtp_accounts:
            log.warning("No SMTP accounts – skipping email layer")
            return 0
        target = evidence.get("username", "target")
        vtypes = ["spam / scam / fraud", "ToS violation", "illegal / harmful content",
                  "copyright", "child safety concern", "violence / graphic content"]
        tasks_planned = []
        for i in range(volume):
            smtp = self.smtp_accounts[i % len(self.smtp_accounts)]
            mailbox = config.TELEGRAM_ABUSE_MAILBOXES[i % len(config.TELEGRAM_ABUSE_MAILBOXES)]
            vtype = random.choice(vtypes)
            subj_t = random.choice(SUBJECTS)
            subject = subj_t.format(target=target, vtype=vtype.split("/")[0].strip(), ts=utc_now())
            body = self._build_body(evidence, vtype)
            if random.random() > 0.5:
                body += "\n\nFollow-up available upon request."
            tasks_planned.append((smtp, mailbox, subject, body))

        log.info(f"Email pressure: {volume} messages across {len(self.smtp_accounts)} SMTP")
        for smtp, to_addr, subject, body in tasks_planned:
            await self._send_one(smtp, to_addr, subject, body)
            await human_delay(config.EMAIL_DELAY_MIN, config.EMAIL_DELAY_MAX)
        log.info(f"Email layer done → sent={self.sent} failed={self.failed}")
        return self.sent
