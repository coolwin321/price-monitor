import asyncio

from flask import Blueprint, jsonify

from db.database import SessionLocal
from db.models import FlightWatch, HotelWatch, PriceRecord, ScraperHealth

prices_bp = Blueprint("prices", __name__, url_prefix="/api")


@prices_bp.route("/dashboard", methods=["GET"])
def dashboard_summary():
    session = SessionLocal()
    try:
        flight_count = session.query(FlightWatch).filter_by(is_active=True).count()
        hotel_count = session.query(HotelWatch).filter_by(is_active=True).count()
        total_prices = session.query(PriceRecord).count()

        # Get latest price per active flight watch
        flight_watches = session.query(FlightWatch).filter_by(is_active=True).all()
        flight_summaries = []
        for w in flight_watches:
            latest = (
                session.query(PriceRecord)
                .filter_by(watch_type="flight", watch_id=w.id)
                .order_by(PriceRecord.scraped_at.desc())
                .first()
            )
            summary = w.to_dict()
            if latest:
                summary["latest_price"] = latest.price
                summary["latest_source"] = latest.source
                summary["latest_scraped_at"] = latest.scraped_at.isoformat()
            flight_summaries.append(summary)

        hotel_watches = session.query(HotelWatch).filter_by(is_active=True).all()
        hotel_summaries = []
        for w in hotel_watches:
            latest = (
                session.query(PriceRecord)
                .filter_by(watch_type="hotel", watch_id=w.id)
                .order_by(PriceRecord.scraped_at.desc())
                .first()
            )
            summary = w.to_dict()
            if latest:
                summary["latest_price"] = latest.price
                summary["latest_source"] = latest.source
                summary["latest_scraped_at"] = latest.scraped_at.isoformat()
            hotel_summaries.append(summary)

        return jsonify({
            "flight_count": flight_count,
            "hotel_count": hotel_count,
            "total_price_records": total_prices,
            "flights": flight_summaries,
            "hotels": hotel_summaries,
        })
    finally:
        session.close()


@prices_bp.route("/health", methods=["GET"])
def scraper_health():
    session = SessionLocal()
    try:
        healths = session.query(ScraperHealth).all()
        return jsonify([
            {
                "scraper_name": h.scraper_name,
                "last_success_at": h.last_success_at.isoformat() if h.last_success_at else None,
                "last_failure_at": h.last_failure_at.isoformat() if h.last_failure_at else None,
                "consecutive_failures": h.consecutive_failures,
                "last_error": h.last_error,
                "is_disabled": h.is_disabled,
            }
            for h in healths
        ])
    finally:
        session.close()


@prices_bp.route("/scrape-now/<watch_type>/<int:watch_id>", methods=["POST"])
def scrape_now(watch_type, watch_id):
    """Trigger an immediate scrape for debugging."""
    from scheduler.jobs import _run_flight_scrapes, _run_hotel_scrapes

    session = SessionLocal()
    try:
        if watch_type == "flight":
            watch = session.query(FlightWatch).get(watch_id)
        elif watch_type == "hotel":
            watch = session.query(HotelWatch).get(watch_id)
        else:
            return jsonify({"error": "Invalid watch_type"}), 400

        if not watch:
            return jsonify({"error": "Watch not found"}), 404
    finally:
        session.close()

    try:
        if watch_type == "flight":
            asyncio.run(_run_flight_scrapes())
        else:
            asyncio.run(_run_hotel_scrapes())
        return jsonify({"status": "scrape triggered"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
