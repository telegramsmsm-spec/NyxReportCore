"""Target content harvester – pull posts, build evidence pack."""
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from telethon import TelegramClient
from telethon.tl.types import Message, Channel, Chat, User

from utils.logger import log
from utils.helpers import normalize_username


class ContentHarvester:
    def __init__(self, client: TelegramClient):
        self.client = client

    async def harvest(self, target: str, limit: int = 80) -> Dict[str, Any]:
        username = normalize_username(target)
        log.info(f"Harvesting content from @{username} (limit={limit})")
        try:
            entity = await self.client.get_entity(username)
        except Exception as e:
            log.error(f"Cannot resolve @{username}: {e}")
            return self._empty_pack(username)

        entity_type = "channel"
        if isinstance(entity, Channel):
            entity_type = "channel" if entity.broadcast else "group"
        elif isinstance(entity, Chat):
            entity_type = "group"
        elif isinstance(entity, User):
            entity_type = "user"

        title = getattr(entity, "title", None) or getattr(entity, "first_name", username)
        participants = getattr(entity, "participants_count", None)

        messages: List[Message] = await self.client.get_messages(entity, limit=limit)
        posts = []
        sample_ids = []
        excerpts = []
        dates = []
        total_views = 0

        for msg in messages:
            if not msg or not isinstance(msg, Message):
                continue
            mid = msg.id
            sample_ids.append(mid)
            text = (msg.message or "")[:300]
            date_str = msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else ""
            if msg.date:
                dates.append(msg.date)
            views = getattr(msg, "views", 0) or 0
            total_views += views
            link = f"https://t.me/{username}/{mid}"
            posts.append({
                "id": mid,
                "text": text,
                "date": date_str,
                "views": views,
                "link": link,
                "has_media": bool(msg.media),
            })
            if text.strip():
                excerpts.append(text.strip()[:120])

        date_range = ""
        if dates:
            dates_sorted = sorted(dates)
            date_range = f"{dates_sorted[0].strftime('%Y-%m-%d')} → {dates_sorted[-1].strftime('%Y-%m-%d')}"

        pack = {
            "username": username,
            "title": title,
            "entity_type": entity_type,
            "link": f"https://t.me/{username}",
            "participants": participants,
            "posts_fetched": len(posts),
            "sample_ids": sample_ids[:20],
            "sample_links": [p["link"] for p in posts[:10]],
            "excerpts": excerpts[:8],
            "date_range": date_range,
            "total_views_sampled": total_views,
            "posts": posts,
            "harvested_at": datetime.now(timezone.utc).isoformat(),
        }
        log.info(f"Evidence pack ready: {len(posts)} posts, type={entity_type}, views≈{total_views}")
        return pack

    def _empty_pack(self, username: str) -> Dict[str, Any]:
        return {
            "username": username,
            "title": username,
            "entity_type": "unknown",
            "link": f"https://t.me/{username}",
            "participants": None,
            "posts_fetched": 0,
            "sample_ids": [],
            "sample_links": [],
            "excerpts": [],
            "date_range": "",
            "total_views_sampled": 0,
            "posts": [],
            "harvested_at": datetime.now(timezone.utc).isoformat(),
        }
