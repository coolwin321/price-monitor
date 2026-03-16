import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///price_monitor.db")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    SCRAPE_INTERVAL_HOURS = int(os.getenv("SCRAPE_INTERVAL_HOURS", "4"))
    ALERT_COOLDOWN_HOURS = int(os.getenv("ALERT_COOLDOWN_HOURS", "6"))
    MAX_CONSECUTIVE_FAILURES = 10
    FAILURE_ALERT_THRESHOLD = 5
    PRICE_RETENTION_DAYS = 90
    MIN_REQUEST_INTERVAL_SECONDS = 60
    DEBUG_SCREENSHOT_LIMIT = 20
