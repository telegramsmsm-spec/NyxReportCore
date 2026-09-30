"""Shared helpers – delays, fingerprints, text variation, proxy parse."""
import asyncio
import random
import re
import string
from typing import Optional, Tuple, Dict, Any
from urllib.parse import urlparse

import config


async def human_delay(lo: float = None, hi: float = None):
    lo = lo if lo is not None else config.REPORT_DELAY_MIN
    hi = hi if hi is not None else config.REPORT_DELAY_MAX
    await asyncio.sleep(random.uniform(lo, hi))


def random_device() -> Dict[str, str]:
    return {
        "device_model": random.choice(config.DEVICE_MODELS),
        "system_version": random.choice(config.SYSTEM_VERSIONS),
        "app_version": random.choice(config.APP_VERSIONS),
        "lang_code": random.choice(["en", "en", "en", "es", "de", "fr", "ru"]),
        "system_lang_code": "en-US",
    }


def weighted_reason() -> str:
    reasons = list(config.REPORT_REASONS.keys())
    weights = list(config.REPORT_REASONS.values())
    return random.choices(reasons, weights=weights, k=1)[0]


def unique_report_comment(reason: str, evidence: Dict[str, Any], target: str) -> str:
    """Generate non-identical report comment referencing real harvested posts."""
    templates = [
        "This {type} is actively distributing {reason} material. See posts {ids}. Immediate action required.",
        "Repeated {reason} violations observed on @{target}. Evidence: messages {ids}. Please review and restrict.",
        "Content on this {type} violates Telegram ToS ({reason}). Sample IDs: {ids}. Request permanent ban.",
        "Multiple users reporting {reason} from @{target}. Direct links and IDs: {ids}. Take down content.",
        "Clear {reason} activity documented. Posts {ids} contain the violating material. Ban requested.",
        "Ongoing {reason} spam/scam pattern. Message IDs for verification: {ids}. Full evidence pack available.",
    ]
    ids = evidence.get("sample_ids", [])[:5]
    id_str = ", ".join(str(i) for i in ids) if ids else "recent posts"
    t = random.choice(templates)
    return t.format(
        type=evidence.get("entity_type", "channel"),
        reason=reason.replace("_", " "),
        target=target.lstrip("@"),
        ids=id_str,
    )


def random_ref_id() -> str:
    return "NX-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=10))


PROXY_RE = re.compile(
    r"(?:(?P<proto>socks5|socks4|http|https|mtproto)://)?"
    r"(?:(?P<user>[^:@\s]+):(?P<pass>[^@\s]+)@)?"
    r"(?P<host>[\w\.\-]+):(?P<port>\d{2,5})",
    re.I,
)


def parse_proxy_line(line: str) -> Optional[Dict[str, Any]]:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    m = PROXY_RE.search(line)
    if not m:
        return None
    d = m.groupdict()
    proto = (d.get("proto") or "socks5").lower()
    if proto == "mtproto":
        return {
            "proto": "mtproto",
            "host": d["host"],
            "port": int(d["port"]),
            "user": d.get("user"),
            "password": d.get("pass"),
            "raw": line,
        }
    return {
        "proto": proto if proto in ("socks5", "socks4", "http", "https") else "socks5",
        "host": d["host"],
        "port": int(d["port"]),
        "user": d.get("user"),
        "password": d.get("pass"),
        "raw": f"{proto}://{d['host']}:{d['port']}" if not d.get("user")
               else f"{proto}://{d['user']}:{d['pass']}@{d['host']}:{d['port']}",
    }


def proxy_to_telethon(proxy: Dict[str, Any]) -> Optional[Tuple]:
    """Return (type, host, port, True, user, password) for Telethon or None."""
    if not proxy or proxy.get("proto") == "mtproto":
        return None
    import socks
    type_map = {
        "socks5": socks.SOCKS5,
        "socks4": socks.SOCKS4,
        "http": socks.HTTP,
        "https": socks.HTTP,
    }
    ptype = type_map.get(proxy["proto"], socks.SOCKS5)
    return (
        ptype,
        proxy["host"],
        proxy["port"],
        True,
        proxy.get("user"),
        proxy.get("password"),
    )


def extract_proxies_from_text(text: str) -> list:
    found = []
    for m in PROXY_RE.finditer(text or ""):
        raw = m.group(0)
        p = parse_proxy_line(raw)
        if p:
            found.append(p)
    return found


def normalize_username(u: str) -> str:
    u = u.strip()
    if u.startswith("https://t.me/"):
        u = u.split("t.me/")[-1].split("/")[0].split("?")[0]
    return u.lstrip("@")
