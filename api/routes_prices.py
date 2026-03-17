import threading

from flask import Blueprint, jsonify

from db.database import SessionLocal
from db.models import FlightWatch, HotelWatch, PriceRecord

prices_bp = Blueprint("prices", __name__, url_prefix="/api")


@prices_bp.route("/dashboard", methods=["GET"])
def dashboard_summary():
    session = SessionLocal()
    try:
        flight_count = session.query(FlightWatch).filter_by(is_active=True).count()
        hotel_count = session.query(HotelWatch).filter_by(is_active=True).count()
        total_prices = session.query(PriceRecord).count()

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


@prices_bp.route("/scrape-now/<watch_type>/<int:watch_id>", methods=["POST"])
def scrape_now(watch_type, watch_id):
    """Trigger an immediate price check for a single watch."""
    from scheduler.jobs import check_single_flight, check_single_hotel

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

    def _run_in_background():
        if watch_type == "flight":
            check_single_flight(watch_id)
        else:
            check_single_hotel(watch_id)

    thread = threading.Thread(target=_run_in_background, daemon=True)
    thread.start()
    return jsonify({"status": "check started", "message": "Check back in ~10 seconds for results"})
