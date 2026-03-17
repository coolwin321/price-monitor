import json
import logging
from datetime import datetime, timedelta

from config import Config
from db.database import SessionLocal
from db.models import FlightWatch, HotelWatch, PriceRecord

logger = logging.getLogger(__name__)


def _store_prices(watch_type: str, watch_id: int, results: list):
    session = SessionLocal()
    try:
        for r in results:
            record = PriceRecord(
                watch_type=watch_type,
                watch_id=watch_id,
                source=r.source,
                price=r.price,
                currency=r.currency,
                raw_details=json.dumps(r.raw_details) if r.raw_details else None,
                scraped_at=r.scraped_at,
            )
            session.add(record)
        session.commit()
    finally:
        session.close()


def _check_flight_watch(watch_id: int, origin: str, dest: str, dep: str, ret: str | None,
                        threshold: float | None, currency: str, return_date_obj):
    """Check a single flight watch via Google Flights."""
    from scrapers.google_flights import search_flights
    from alerts.telegram import evaluate_and_alert_flight_sync

    try:
        results = search_flights(origin, dest, dep, ret)
        if results:
            _store_prices("flight", watch_id, results)
            cheapest = min(results, key=lambda r: r.price)
            class W:
                pass
            w = W()
            w.id, w.origin, w.destination = watch_id, origin, dest
            w.departure_date, w.return_date = dep, return_date_obj
            w.threshold_price, w.currency = threshold, currency
            evaluate_and_alert_flight_sync(w, cheapest)
            logger.info(f"[flights] {origin}->{dest}: cheapest ${cheapest.price:.0f}")
        else:
            logger.warning(f"[flights] {origin}->{dest}: no results")
    except Exception as e:
        logger.error(f"[flights] Error checking {origin}->{dest}: {e}")


def _check_hotel_watch(watch_id: int, name: str, loc: str, checkin: str, checkout: str,
                       threshold: float | None, currency: str):
    """Check a single hotel watch via Google Hotels."""
    from scrapers.google_hotels import search_hotels
    from alerts.telegram import evaluate_and_alert_hotel_sync

    try:
        results = search_hotels(name, loc, checkin, checkout)
        if results:
            _store_prices("hotel", watch_id, results)
            cheapest = min(results, key=lambda r: r.price)
            class W:
                pass
            w = W()
            w.id, w.hotel_name, w.location = watch_id, name, loc
            w.checkin_date, w.checkout_date = checkin, checkout
            w.threshold_price, w.currency = threshold, currency
            evaluate_and_alert_hotel_sync(w, cheapest)
            logger.info(f"[hotels] {name}: cheapest ${cheapest.price:.0f}/night")
        else:
            logger.warning(f"[hotels] {name}: no results")
    except Exception as e:
        logger.error(f"[hotels] Error checking {name}: {e}")


def check_all_watches():
    """Check all active flight and hotel watches. Entry point for APScheduler."""
    logger.info("Starting price check for all watches...")

    session = SessionLocal()
    try:
        flights = session.query(FlightWatch).filter_by(is_active=True).all()
        flight_data = [(w.id, w.origin, w.destination, str(w.departure_date),
                        str(w.return_date) if w.return_date else None,
                        w.threshold_price, w.currency, w.return_date) for w in flights]

        hotels = session.query(HotelWatch).filter_by(is_active=True).all()
        hotel_data = [(w.id, w.hotel_name, w.location, str(w.checkin_date),
                       str(w.checkout_date), w.threshold_price, w.currency) for w in hotels]
    finally:
        session.close()

    for fd in flight_data:
        _check_flight_watch(*fd)

    for hd in hotel_data:
        _check_hotel_watch(*hd)

    logger.info(f"Price check complete: {len(flight_data)} flights, {len(hotel_data)} hotels")


def check_single_flight(watch_id: int):
    """Check a single flight watch on demand."""
    session = SessionLocal()
    try:
        w = session.query(FlightWatch).get(watch_id)
        if not w or not w.is_active:
            return {"status": "error", "message": "Watch not found or inactive"}
        data = (w.id, w.origin, w.destination, str(w.departure_date),
                str(w.return_date) if w.return_date else None,
                w.threshold_price, w.currency, w.return_date)
    finally:
        session.close()

    _check_flight_watch(*data)
    return {"status": "ok"}


def check_single_hotel(watch_id: int):
    """Check a single hotel watch on demand."""
    session = SessionLocal()
    try:
        w = session.query(HotelWatch).get(watch_id)
        if not w or not w.is_active:
            return {"status": "error", "message": "Watch not found or inactive"}
        data = (w.id, w.hotel_name, w.location, str(w.checkin_date),
                str(w.checkout_date), w.threshold_price, w.currency)
    finally:
        session.close()

    _check_hotel_watch(*data)
    return {"status": "ok"}


def cleanup_old_prices():
    """Delete price records older than retention period."""
    session = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=Config.PRICE_RETENTION_DAYS)
        deleted = session.query(PriceRecord).filter(PriceRecord.scraped_at < cutoff).delete()
        session.commit()
        logger.info(f"Cleaned up {deleted} old price records")
    finally:
        session.close()
