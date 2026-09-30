# NyxReportCore

Production-ready Telegram full-spectrum reporting MVP.

**Layers (all fire together):**
1. Multi-account inside-Telegram reports (Telethon)
2. Official bot escalation (`@AbuseNotification`, `@SearchReport`, `@NoToScam`)
3. Outside email pressure to Telegram abuse / legal / DMCA mailboxes
4. Live content harvesting from any public target
5. Continuous proxy harvesting from operator-supplied proxy channels

## Stack
- Python 3.11+
- Telethon, asyncio, aiosmtplib, aiohttp, python-socks, aiosqlite, colorama

## Setup

```bash
cd NyxReportCore
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Optional (better proxy testing):
```bash
pip install aiohttp-socks
```

## Config files (fill these – zero secrets in code)

### `data/accounts.json`
```json
[
  {
    "phone": "+1234567890",
    "api_id": 12345678,
    "api_hash": "your_hash",
    "session_name": "acc_001",
    "string_session": null,
    "2fa": null,
    "proxy": "socks5://user:pass@host:port"
  }
]
```
- Get `api_id` / `api_hash` from https://my.telegram.org
- First run will create `.session` files next to the project (or use `string_session`)
- Optional sticky proxy per account

### `data/smtp.json`
```json
[
  {
    "host": "smtp.example.com",
    "port": 587,
    "user": "you@example.com",
    "password": "pass",
    "from_name": "Compliance Desk",
    "use_tls": true
  }
]
```

### `data/proxies.txt` (optional seed)
```
socks5://user:pass@1.2.3.4:1080
http://5.6.7.8:8080
```
Live harvester continuously adds more from `--proxy-channels`.

## Run

```bash
python main.py --target @badchannel --proxy-channels @proxychannel1 @proxychannel2 --emails 100 --posts 80 --reports-per-account 8
```

### Flags
| Flag | Default | Meaning |
|------|---------|---------|
| `--target` | required | @username or t.me link |
| `--proxy-channels` | [] | channels that post proxies |
| `--emails` | 100 | outbound abuse emails |
| `--posts` | 80 | posts to harvest for evidence |
| `--reports-per-account` | 8 | max reports per account this wave |

## Execution order
1. Load accounts + seed proxies
2. Health-check → quarantine dead/banned
3. Start keep-alive + continuous proxy harvester
4. Harvest target posts → evidence pack
5. Parallel: inside report wave + official bots + email flood
6. Cleanup + final summary

## Logs
- Colored console
- Full file: `logs/nyx_report.log`
- State DB: `data/nyx_state.db` (accounts, proxies, campaign history)

## Safety built-in
- Per-account report cap
- Human delays 4–15 s
- FloodWait auto-sleep + global pause
- Sticky proxy per account
- Device fingerprint variation
- Dead proxy / dead account quarantine

## Project layout
```
NyxReportCore/
├── main.py
├── config.py
├── requirements.txt
├── README.md
├── data/
│   ├── accounts.json
│   ├── smtp.json
│   └── proxies.txt
├── modules/
│   ├── account_pool.py
│   ├── proxy_harvester.py
│   ├── content_harvester.py
│   ├── report_engine.py
│   ├── bot_escalation.py
│   └── email_pressure.py
├── utils/
│   ├── logger.py
│   ├── db.py
│   └── helpers.py
└── logs/
```

Fill the three config files, install deps, run the one-liner. All layers connect and operate end-to-end.
