"""
NyxReportCore – central configuration.
All tunables live here. No secrets hardcoded.
"""
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ACCOUNTS_FILE = DATA_DIR / "accounts.json"
SMTP_FILE = DATA_DIR / "smtp.json"
PROXIES_FILE = DATA_DIR / "proxies.txt"
DB_PATH = DATA_DIR / "nyx_state.db"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "nyx_report.log"

# Account pool
SESSION_KEEPALIVE_MIN = 30          # minutes
SESSION_KEEPALIVE_MAX = 45
MAX_REPORTS_PER_ACCOUNT_WAVE = 8
ACCOUNT_HEALTH_TIMEOUT = 25         # seconds for health check

# Workers & rate limits
REPORT_WORKERS = 10                 # concurrent inside-Telegram report workers
REPORT_DELAY_MIN = 4.0              # human-like delay between reports (sec)
REPORT_DELAY_MAX = 15.0
FLOODWAIT_PAUSE_GLOBAL = 120        # seconds to pause all workers on mass FloodWait

# Content harvester
DEFAULT_POSTS = 80
MAX_POSTS = 200

# Proxy harvester
PROXY_REFRESH_SECONDS = 180         # re-scrape proxy channels every N seconds
PROXY_TEST_TIMEOUT = 12
PROXY_MAX_ALIVE = 500

# Email pressure
DEFAULT_EMAILS = 100
EMAIL_DELAY_MIN = 1.5
EMAIL_DELAY_MAX = 6.0
SMTP_TIMEOUT = 30

# Official bots (Telegram usernames)
ABUSE_BOT = "AbuseNotification"
SEARCH_REPORT_BOT = "SearchReport"
NOTOSCAM_BOT = "NoToScam"

# Report reason weights (higher = more frequent)
REPORT_REASONS = {
    "child_abuse": 35,
    "spam": 20,
    "violence": 15,
    "pornography": 12,
    "scam": 10,
    "copyright": 5,
    "other": 3,
}

# Device fingerprint pools for Telethon
DEVICE_MODELS = [
    "Samsung Galaxy S23", "Samsung Galaxy S24", "Google Pixel 8",
    "Xiaomi 14", "OnePlus 12", "iPhone 15 Pro", "iPhone 14",
    "Huawei P60", "OPPO Find X7", "Realme GT5",
]
SYSTEM_VERSIONS = [
    "Android 14", "Android 13", "Android 12", "iOS 17.4", "iOS 16.6",
]
APP_VERSIONS = [
    "10.14.5", "10.13.2", "10.12.0", "10.11.4", "11.0.1",
]

# Email targets
TELEGRAM_ABUSE_MAILBOXES = [
    "abuse@telegram.org",
    "stopCA@telegram.org",
    "dmca@telegram.org",
    "support@telegram.org",
    "legal@telegram.org",
    "privacy@telegram.org",
]

# Logging
LOG_LEVEL = "INFO"
CONSOLE_COLORS = True
