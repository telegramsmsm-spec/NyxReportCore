#!/usr/bin/env python3
"""
NyxReportCore – full-spectrum Telegram reporting MVP.
One command. All layers. Zero gaps.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from utils.logger import log, utc_now
from utils.db import StateDB
from modules.account_pool import AccountPool
from modules.proxy_harvester import ProxyHarvester
from modules.content_harvester import ContentHarvester
from modules.report_engine import ReportEngine
from modules.bot_escalation import BotEscalation
from modules.email_pressure import EmailPressure
from utils.helpers import normalize_username


async def run_campaign(args):
    target = normalize_username(args.target)
    proxy_channels = [normalize_username(c) for c in (args.proxy_channels or [])]
    posts = min(args.posts, config.MAX_POSTS)
    emails = args.emails
    rpa = args.reports_per_account

    log.info("=" * 60)
    log.info(f"NyxReportCore START  target=@{target}  {utc_now()}")
    log.info(f"posts={posts}  emails={emails}  reports/acc={rpa}  proxy_ch={proxy_channels}")
    log.info("=" * 60)

    db = StateDB()
    await db.connect()
    campaign_id = await db.start_campaign(target)

    pool = AccountPool(db)
    pool.load_from_file()
    if not pool.accounts:
        log.error("No accounts loaded. Fill data/accounts.json")
        await db.close()
        return

    alive = await pool.health_check_all()
    if not alive:
        log.error("Zero alive accounts after health check. Abort.")
        await db.finish_campaign(campaign_id, 0, 0, 0, 0, "no alive accounts")
        await db.close()
        return

    pool.start_keepalive()

    harvester_client = alive[0].client
    proxy_h = ProxyHarvester(harvester_client, db, proxy_channels)
    await proxy_h.load_seed_file()
    if proxy_channels:
        proxy_h.start()
        log.info("Live proxy harvester running in background")

    free = await db.get_free_proxies(limit=len(alive))
    for acc, px in zip([a for a in alive if not a.proxy_raw], free):
        pool.assign_proxy(acc, px)
        await db.assign_proxy(px, acc.phone)

    content_h = ContentHarvester(harvester_client)
    evidence = await content_h.harvest(target, limit=posts)
    if evidence["posts_fetched"] == 0:
        log.warning("No posts harvested – continuing with peer-level reports only")

    report_engine = ReportEngine(db, campaign_id)
    bot_layer = BotEscalation()
    email_layer = EmailPressure()
    email_layer.load()

    async def reports_job():
        return await report_engine.run_wave(alive, target, evidence, reports_per_account=rpa)

    async def bots_job():
        return await bot_layer.run(alive, target, evidence)

    async def emails_job():
        return await email_layer.run(evidence, volume=emails)

    log.info("Launching report wave + bot escalation + email pressure…")
    results = await asyncio.gather(
        reports_job(), bots_job(), emails_job(), return_exceptions=True,
    )

    reports_ok, reports_fail = 0, 0
    bots_n, emails_n = 0, 0
    if isinstance(results[0], tuple):
        reports_ok, reports_fail = results[0]
    else:
        log.error(f"Report wave exception: {results[0]}")
    if isinstance(results[1], int):
        bots_n = results[1]
    else:
        log.error(f"Bot layer exception: {results[1]}")
    if isinstance(results[2], int):
        emails_n = results[2]
    else:
        log.error(f"Email layer exception: {results[2]}")

    if proxy_channels:
        await proxy_h.stop()
    await pool.stop()

    notes = f"alive_at_end={len(pool.get_alive())}"
    await db.finish_campaign(campaign_id, reports_ok, reports_fail, emails_n, bots_n, notes)
    await db.close()

    log.info("=" * 60)
    log.info("CAMPAIGN SUMMARY")
    log.info(f"  Target           : @{target}")
    log.info(f"  Reports OK       : {reports_ok}")
    log.info(f"  Reports FAIL     : {reports_fail}")
    log.info(f"  Bot messages     : {bots_n}")
    log.info(f"  Emails sent      : {emails_n}")
    log.info(f"  Accounts alive   : {len([a for a in pool.accounts if a.status == 'alive'])}")
    log.info(f"  Evidence posts   : {evidence.get('posts_fetched', 0)}")
    log.info(f"  Finished         : {utc_now()}")
    log.info("=" * 60)


def build_parser():
    p = argparse.ArgumentParser(
        description="NyxReportCore – Telegram full-spectrum reporting MVP",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--target", required=True, help="Target @username or t.me link")
    p.add_argument("--proxy-channels", nargs="*", default=[],
                   help="One or more Telegram channels that post proxies")
    p.add_argument("--emails", type=int, default=config.DEFAULT_EMAILS,
                   help="Number of abuse emails to send")
    p.add_argument("--posts", type=int, default=config.DEFAULT_POSTS,
                   help="How many recent posts to harvest for evidence")
    p.add_argument("--reports-per-account", type=int, default=config.MAX_REPORTS_PER_ACCOUNT_WAVE,
                   help="Max reports each account sends in this wave")
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        asyncio.run(run_campaign(args))
    except KeyboardInterrupt:
        log.warning("Interrupted by operator")
    except Exception as e:
        log.error(f"Fatal: {e}")
        raise


if __name__ == "__main__":
    main()
