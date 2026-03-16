import asyncio
import functools
import logging
import os
import random
import time
from datetime import datetime

from config import Config

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 OPR/108.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
]

# Per-site rate limiting
_last_request_times: dict[str, float] = {}


def get_random_ua() -> str:
    return random.choice(USER_AGENTS)


def get_random_viewport() -> dict:
    return {
        "width": random.randint(1280, 1440),
        "height": random.randint(800, 900),
    }


async def random_delay(min_sec: float = 2.0, max_sec: float = 8.0):
    delay = random.uniform(min_sec, max_sec)
    await asyncio.sleep(delay)


def can_scrape(scraper_name: str) -> bool:
    last_time = _last_request_times.get(scraper_name, 0)
    elapsed = time.time() - last_time
    return elapsed >= Config.MIN_REQUEST_INTERVAL_SECONDS


def mark_scraped(scraper_name: str):
    _last_request_times[scraper_name] = time.time()


def validate_price(price: float, min_price: float = 1.0, max_price: float = 50000.0) -> bool:
    return min_price <= price <= max_price


def parse_price(text: str) -> float | None:
    cleaned = text.strip()
    # Remove common currency symbols and whitespace
    for char in ["$", "€", "£", "¥", "₹", "HK$", "S$", "A$", "C$", "NZ$", ",", " ", "\xa0"]:
        cleaned = cleaned.replace(char, "")
    try:
        return float(cleaned)
    except ValueError:
        return None


async def save_debug_screenshot(page, scraper_name: str):
    debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "debug")
    os.makedirs(debug_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{scraper_name}_{timestamp}.png"
    filepath = os.path.join(debug_dir, filename)

    try:
        await page.screenshot(path=filepath, full_page=False)
        logger.info(f"Debug screenshot saved: {filepath}")
    except Exception as e:
        logger.error(f"Failed to save debug screenshot: {e}")

    # Cleanup: keep only the latest N screenshots per scraper
    _cleanup_screenshots(debug_dir, scraper_name, Config.DEBUG_SCREENSHOT_LIMIT)


def _cleanup_screenshots(debug_dir: str, scraper_name: str, limit: int):
    files = sorted(
        [f for f in os.listdir(debug_dir) if f.startswith(scraper_name) and f.endswith(".png")]
    )
    while len(files) > limit:
        oldest = files.pop(0)
        try:
            os.remove(os.path.join(debug_dir, oldest))
        except OSError:
            pass


def retry_scrape(max_retries: int = 2, backoff_base: int = 30):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait = backoff_base * (2 ** attempt)
                        logger.warning(
                            f"Scrape attempt {attempt + 1} failed: {e}. "
                            f"Retrying in {wait}s..."
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(
                            f"All {max_retries + 1} scrape attempts failed: {e}"
                        )
            raise last_exception

        return wrapper

    return decorator
