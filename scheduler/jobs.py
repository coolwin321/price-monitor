import asyncio
import json
import logging
import random
import time
from datetime import datetime, timedelta

from config import Config
from db.database import SessionLocal
from db.models import FlightWatch, HotelWatch, PriceRecord, ScraperHealth

logger = logging.getLogger(__name__)


def _get_flight_scrapers():
    from scrapers.flights.trip_flights import TripFlightScraper
    from scrapers.flights.skyscanner_flights import SkyscannerFlightScraper
    return [TripFlightScraper(), SkyscannerFlightScraper()]


def _get_hotel_scrapers():
    from scrapers.hotels.trip_hotels import TripHotelScraper
    from scrapers.hotels.agoda_hotels import AgodaHotelScraper
    return [TripHotelScraper(), AgodaHotelScraper()]


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


def _update_scraper_health(scraper_name: str, success: bool, error: str | None = None):
    session = SessionLocal()
    try:
        health = session.query(ScraperHealth).filter_by(scraper_name=scraper_name).first()
        if not health:
            health = ScraperHealth(scraper_name=scraper_name)
            session.add(health)

        if success:
            health.last_success_at = datetime.utcnow()
            health.consecutive_failures = 0
        else:
            health.last_failure_at = datetime.utcnow()
            health.consecutive_failures += 1
            health.last_error = error[:500] if error else None

            if health.consecutive_failures >= Config.MAX_CONSECUTIVE_FAILURES:
                health.is_disabled = True
                logger.warning(f"Auto-disabled scraper: {scraper_name}")

        session.commit()

        # Send alert if failures hit threshold
        if not success and health.consecutive_failures == Config.FAILURE_ALERT_THRESHOLD:
            from alerts.telegram import send_scraper_broken_alert
            asyncio.run(send_scraper_broken_alert(scraper_name, health.consecutive_failures, error or "Unknown"))

    finally:
        session.close()


def _is_scraper_disabled(scraper_name: str) -> bool:
    session = SessionLocal()
    try:
        health = session.query(ScraperHealth).filter_by(scraper_name=scraper_name).first()
        return health.is_disabled if health else False
    finally:
        session.close()


async def _create_browser_context(playwright_instance):
    from playwright_stealth import stealth_async
    from scrapers.utils import get_random_ua, get_random_viewport

    browser = await playwright_instance.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent=get_random_ua(),
        viewport=get_random_viewport(),
        locale="en-US",
    )
    context.on("page", lambda page: asyncio.ensure_future(stealth_async(page)))
    return browser, context


async def _run_flight_scrapes():
    session = SessionLocal()
    try:
        watches = session.query(FlightWatch).filter_by(is_active=True).all()
        watch_data = [(w.id, w.origin, w.destination, str(w.departure_date),
                       str(w.return_date) if w.return_date else None,
                       w.threshold_price, w.currency, w.return_date) for w in watches]
    finally:
        session.close()

    if not watch_data:
        logger.info("No active flight watches")
        return

    from scrapers.utils import can_scrape
    from alerts.telegram import evaluate_and_alert_flight
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser, context = await _create_browser_context(p)
        try:
            for watch_tuple in watch_data:
                wid, origin, dest, dep, ret, threshold, currency, return_date_obj = watch_tuple

                for scraper in _get_flight_scrapers():
                    if _is_scraper_disabled(scraper.SCRAPER_NAME):
                        logger.info(f"Skipping disabled scraper: {scraper.SCRAPER_NAME}")
                        continue
                    if not can_scrape(scraper.SCRAPER_NAME):
                        logger.info(f"Rate limited: {scraper.SCRAPER_NAME}")
                        continue

                    try:
                        results = await scraper.scrape_flight(
                            origin, dest, dep, ret,
                            browser_context=context,
                        )
                        if results:
                            _store_prices("flight", wid, results)
                            _update_scraper_health(scraper.SCRAPER_NAME, success=True)

                            cheapest = min(results, key=lambda r: r.price)

                            class WatchProxy:
                                pass
                            wp = WatchProxy()
                            wp.id = wid
                            wp.origin = origin
                            wp.destination = dest
                            wp.departure_date = dep
                            wp.return_date = return_date_obj
                            wp.threshold_price = threshold
                            wp.currency = currency
                            await evaluate_and_alert_flight(wp, cheapest)
                        else:
                            _update_scraper_health(scraper.SCRAPER_NAME, success=False, error="No results returned")
                    except Exception as e:
                        _update_scraper_health(scraper.SCRAPER_NAME, success=False, error=str(e))

                    await asyncio.sleep(random.uniform(60, 120))
        finally:
            await browser.close()


async def _run_hotel_scrapes():
    session = SessionLocal()
    try:
        watches = session.query(HotelWatch).filter_by(is_active=True).all()
        watch_data = [(w.id, w.hotel_name, w.location, str(w.checkin_date),
                       str(w.checkout_date), w.threshold_price, w.currency) for w in watches]
    finally:
        session.close()

    if not watch_data:
        logger.info("No active hotel watches")
        return

    from scrapers.utils import can_scrape
    from alerts.telegram import evaluate_and_alert_hotel
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser, context = await _create_browser_context(p)
        try:
            for watch_tuple in watch_data:
                wid, name, loc, checkin, checkout, threshold, currency = watch_tuple

                for scraper in _get_hotel_scrapers():
                    if _is_scraper_disabled(scraper.SCRAPER_NAME):
                        continue
                    if not can_scrape(scraper.SCRAPER_NAME):
                        continue

                    try:
                        results = await scraper.scrape_hotel(
                            name, loc, checkin, checkout,
                            browser_context=context,
                        )
                        if results:
                            _store_prices("hotel", wid, results)
                            _update_scraper_health(scraper.SCRAPER_NAME, success=True)

                            cheapest = min(results, key=lambda r: r.price)

                            class WatchProxy:
                                pass
                            wp = WatchProxy()
                            wp.id = wid
                            wp.hotel_name = name
                            wp.location = loc
                            wp.checkin_date = checkin
                            wp.checkout_date = checkout
                            wp.threshold_price = threshold
                            wp.currency = currency
                            await evaluate_and_alert_hotel(wp, cheapest)
                        else:
                            _update_scraper_health(scraper.SCRAPER_NAME, success=False, error="No results returned")
                    except Exception as e:
                        _update_scraper_health(scraper.SCRAPER_NAME, success=False, error=str(e))

                    await asyncio.sleep(random.uniform(60, 120))
        finally:
            await browser.close()


async def _run_single_flight_scrape(watch_id: int):
    """Scrape a single flight watch immediately."""
    session = SessionLocal()
    try:
        w = session.query(FlightWatch).get(watch_id)
        if not w or not w.is_active:
            return {"status": "error", "message": "Watch not found or inactive"}
        watch_data = (w.id, w.origin, w.destination, str(w.departure_date),
                      str(w.return_date) if w.return_date else None,
                      w.threshold_price, w.currency, w.return_date)
    finally:
        session.close()

    from scrapers.utils import can_scrape
    from alerts.telegram import evaluate_and_alert_flight
    from playwright.async_api import async_playwright

    wid, origin, dest, dep, ret, threshold, currency, return_date_obj = watch_data
    total_results = 0

    async with async_playwright() as p:
        browser, context = await _create_browser_context(p)
        try:
            for scraper in _get_flight_scrapers():
                if _is_scraper_disabled(scraper.SCRAPER_NAME):
                    continue
                try:
                    results = await scraper.scrape_flight(
                        origin, dest, dep, ret, browser_context=context,
                    )
                    if results:
                        _store_prices("flight", wid, results)
                        _update_scraper_health(scraper.SCRAPER_NAME, success=True)
                        total_results += len(results)
                        cheapest = min(results, key=lambda r: r.price)
                        class WatchProxy:
                            pass
                        wp = WatchProxy()
                        wp.id, wp.origin, wp.destination = wid, origin, dest
                        wp.departure_date, wp.return_date = dep, return_date_obj
                        wp.threshold_price, wp.currency = threshold, currency
                        await evaluate_and_alert_flight(wp, cheapest)
                    else:
                        _update_scraper_health(scraper.SCRAPER_NAME, success=False, error="No results returned")
                except Exception as e:
                    _update_scraper_health(scraper.SCRAPER_NAME, success=False, error=str(e))
                await asyncio.sleep(random.uniform(5, 15))
        finally:
            await browser.close()

    return {"status": "ok", "results": total_results}


async def _run_single_hotel_scrape(watch_id: int):
    """Scrape a single hotel watch immediately."""
    session = SessionLocal()
    try:
        w = session.query(HotelWatch).get(watch_id)
        if not w or not w.is_active:
            return {"status": "error", "message": "Watch not found or inactive"}
        watch_data = (w.id, w.hotel_name, w.location, str(w.checkin_date),
                      str(w.checkout_date), w.threshold_price, w.currency)
    finally:
        session.close()

    from scrapers.utils import can_scrape
    from alerts.telegram import evaluate_and_alert_hotel
    from playwright.async_api import async_playwright

    wid, name, loc, checkin, checkout, threshold, currency = watch_data
    total_results = 0

    async with async_playwright() as p:
        browser, context = await _create_browser_context(p)
        try:
            for scraper in _get_hotel_scrapers():
                if _is_scraper_disabled(scraper.SCRAPER_NAME):
                    continue
                try:
                    results = await scraper.scrape_hotel(
                        name, loc, checkin, checkout, browser_context=context,
                    )
                    if results:
                        _store_prices("hotel", wid, results)
                        _update_scraper_health(scraper.SCRAPER_NAME, success=True)
                        total_results += len(results)
                        cheapest = min(results, key=lambda r: r.price)
                        class WatchProxy:
                            pass
                        wp = WatchProxy()
                        wp.id, wp.hotel_name, wp.location = wid, name, loc
                        wp.checkin_date, wp.checkout_date = checkin, checkout
                        wp.threshold_price, wp.currency = threshold, currency
                        await evaluate_and_alert_hotel(wp, cheapest)
                    else:
                        _update_scraper_health(scraper.SCRAPER_NAME, success=False, error="No results returned")
                except Exception as e:
                    _update_scraper_health(scraper.SCRAPER_NAME, success=False, error=str(e))
                await asyncio.sleep(random.uniform(5, 15))
        finally:
            await browser.close()

    return {"status": "ok", "results": total_results}


def check_all_flights():
    """Entry point for APScheduler."""
    logger.info("Starting flight price check...")
    asyncio.run(_run_flight_scrapes())
    logger.info("Flight price check complete")


def check_all_hotels():
    """Entry point for APScheduler."""
    logger.info("Starting hotel price check...")
    asyncio.run(_run_hotel_scrapes())
    logger.info("Hotel price check complete")


def health_check():
    """Re-enable scrapers that have been disabled for 24+ hours."""
    session = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        disabled = session.query(ScraperHealth).filter_by(is_disabled=True).all()
        for h in disabled:
            if h.last_failure_at and h.last_failure_at < cutoff:
                h.is_disabled = False
                h.consecutive_failures = 0
                logger.info(f"Re-enabled scraper: {h.scraper_name}")
        session.commit()
    finally:
        session.close()


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
