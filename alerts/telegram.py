import logging
from datetime import datetime, timedelta

import httpx

from config import Config
from db.database import SessionLocal
from db.models import AlertSent

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"


def send_telegram_message_sync(message: str) -> bool:
    if not Config.TELEGRAM_BOT_TOKEN or not Config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured, skipping alert")
        return False

    url = f"{TELEGRAM_API.format(token=Config.TELEGRAM_BOT_TOKEN)}/sendMessage"
    payload = {
        "chat_id": Config.TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        resp = httpx.post(url, json=payload, timeout=10.0)
        resp.raise_for_status()
        logger.info("Telegram alert sent successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")
        return False


def should_send_alert(watch_type: str, watch_id: int, current_price: float) -> bool:
    session = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=Config.ALERT_COOLDOWN_HOURS)
        recent = (
            session.query(AlertSent)
            .filter(
                AlertSent.watch_type == watch_type,
                AlertSent.watch_id == watch_id,
                AlertSent.sent_at >= cutoff,
                AlertSent.price <= current_price,
            )
            .first()
        )
        return recent is None
    finally:
        session.close()


def record_alert(watch_type: str, watch_id: int, price: float, source: str, message: str):
    session = SessionLocal()
    try:
        alert = AlertSent(
            watch_type=watch_type,
            watch_id=watch_id,
            price=price,
            source=source,
            message=message,
        )
        session.add(alert)
        session.commit()
    finally:
        session.close()


def evaluate_and_alert_flight_sync(watch, price_result):
    if watch.threshold_price is None:
        return
    if price_result.price > watch.threshold_price:
        return
    if not should_send_alert("flight", watch.id, price_result.price):
        return

    message = (
        f"*Flight Price Drop!*\n"
        f"`{watch.origin}` -> `{watch.destination}`\n"
        f"{watch.departure_date}"
    )
    if watch.return_date:
        message += f" -> {watch.return_date}"
    message += (
        f"\n*{watch.currency} {price_result.price:.0f}* on {price_result.source}\n"
        f"Threshold: {watch.currency} {watch.threshold_price:.0f}"
    )
    if price_result.raw_details.get("airline"):
        message += f"\n{price_result.raw_details['airline']}"

    sent = send_telegram_message_sync(message)
    if sent:
        record_alert("flight", watch.id, price_result.price, price_result.source, message)


def evaluate_and_alert_hotel_sync(watch, price_result):
    if watch.threshold_price is None:
        return
    if price_result.price > watch.threshold_price:
        return
    if not should_send_alert("hotel", watch.id, price_result.price):
        return

    message = (
        f"*Hotel Price Drop!*\n"
        f"`{watch.hotel_name}` in {watch.location}\n"
        f"{watch.checkin_date} -> {watch.checkout_date}\n"
        f"*{watch.currency} {price_result.price:.0f}/night* on {price_result.source}\n"
        f"Threshold: {watch.currency} {watch.threshold_price:.0f}"
    )

    sent = send_telegram_message_sync(message)
    if sent:
        record_alert("hotel", watch.id, price_result.price, price_result.source, message)
