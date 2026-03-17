import json
import logging
import os
from datetime import datetime

from flask import Flask, redirect, render_template, request, flash, url_for
from apscheduler.schedulers.background import BackgroundScheduler

from config import Config
from db.database import init_db, SessionLocal
from db.models import FlightWatch, HotelWatch, PriceRecord
from api.routes_flights import flights_bp
from api.routes_hotels import hotels_bp
from api.routes_prices import prices_bp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = Config.SECRET_KEY

    # Register API blueprints
    app.register_blueprint(flights_bp)
    app.register_blueprint(hotels_bp)
    app.register_blueprint(prices_bp)

    # Initialize database
    init_db()

    # --- Web routes ---

    @app.route("/")
    def dashboard():
        session = SessionLocal()
        try:
            flights = session.query(FlightWatch).filter_by(is_active=True).all()
            hotels = session.query(HotelWatch).filter_by(is_active=True).all()

            flight_data = []
            for w in flights:
                d = w.to_dict()
                latest = (
                    session.query(PriceRecord)
                    .filter_by(watch_type="flight", watch_id=w.id)
                    .order_by(PriceRecord.scraped_at.desc())
                    .first()
                )
                if latest:
                    d["latest_price"] = latest.price
                    d["latest_source"] = latest.source
                else:
                    d["latest_price"] = None
                    d["latest_source"] = None
                flight_data.append(d)

            hotel_data = []
            for w in hotels:
                d = w.to_dict()
                latest = (
                    session.query(PriceRecord)
                    .filter_by(watch_type="hotel", watch_id=w.id)
                    .order_by(PriceRecord.scraped_at.desc())
                    .first()
                )
                if latest:
                    d["latest_price"] = latest.price
                    d["latest_source"] = latest.source
                else:
                    d["latest_price"] = None
                    d["latest_source"] = None
                hotel_data.append(d)

            total_watches = len(flight_data) + len(hotel_data)
            return render_template("dashboard.html", flights=flight_data, hotels=hotel_data,
                                   total_watches=total_watches, max_watches=Config.MAX_WATCHES)
        finally:
            session.close()

    def _active_watch_count(session):
        return (session.query(FlightWatch).filter_by(is_active=True).count() +
                session.query(HotelWatch).filter_by(is_active=True).count())

    @app.route("/flights/new", methods=["GET", "POST"])
    def add_flight():
        if request.method == "POST":
            session = SessionLocal()
            try:
                if _active_watch_count(session) >= Config.MAX_WATCHES:
                    flash(f"Maximum {Config.MAX_WATCHES} active watches allowed. Delete one first.", "error")
                    return redirect(url_for("add_flight"))

                watch = FlightWatch(
                    origin=request.form["origin"].upper().strip(),
                    destination=request.form["destination"].upper().strip(),
                    departure_date=datetime.strptime(request.form["departure_date"], "%Y-%m-%d").date(),
                    return_date=(
                        datetime.strptime(request.form["return_date"], "%Y-%m-%d").date()
                        if request.form.get("return_date")
                        else None
                    ),
                    threshold_price=(
                        float(request.form["threshold_price"])
                        if request.form.get("threshold_price")
                        else None
                    ),
                    currency=request.form.get("currency", "USD"),
                )
                session.add(watch)
                session.commit()
                flash("Flight watch added!", "success")
                return redirect(url_for("dashboard"))
            finally:
                session.close()
        return render_template("add_flight.html")

    @app.route("/hotels/new", methods=["GET", "POST"])
    def add_hotel():
        if request.method == "POST":
            session = SessionLocal()
            try:
                if _active_watch_count(session) >= Config.MAX_WATCHES:
                    flash(f"Maximum {Config.MAX_WATCHES} active watches allowed. Delete one first.", "error")
                    return redirect(url_for("add_hotel"))

                watch = HotelWatch(
                    hotel_name=request.form["hotel_name"].strip(),
                    location=request.form["location"].strip(),
                    checkin_date=datetime.strptime(request.form["checkin_date"], "%Y-%m-%d").date(),
                    checkout_date=datetime.strptime(request.form["checkout_date"], "%Y-%m-%d").date(),
                    threshold_price=(
                        float(request.form["threshold_price"])
                        if request.form.get("threshold_price")
                        else None
                    ),
                    currency=request.form.get("currency", "USD"),
                )
                session.add(watch)
                session.commit()
                flash("Hotel watch added!", "success")
                return redirect(url_for("dashboard"))
            finally:
                session.close()
        return render_template("add_hotel.html")

    @app.route("/watches/<watch_type>/<int:watch_id>")
    def watch_detail(watch_type, watch_id):
        session = SessionLocal()
        try:
            if watch_type == "flight":
                watch = session.query(FlightWatch).get(watch_id)
                title = f"{watch.origin} → {watch.destination}" if watch else "Not Found"
            elif watch_type == "hotel":
                watch = session.query(HotelWatch).get(watch_id)
                title = f"{watch.hotel_name}" if watch else "Not Found"
            else:
                return "Invalid watch type", 404

            if not watch:
                return "Watch not found", 404

            prices = (
                session.query(PriceRecord)
                .filter_by(watch_type=watch_type, watch_id=watch_id)
                .order_by(PriceRecord.scraped_at.desc())
                .limit(200)
                .all()
            )

            prices_json = json.dumps([
                {
                    "source": p.source,
                    "price": p.price,
                    "currency": p.currency,
                    "scraped_at": p.scraped_at.isoformat(),
                }
                for p in prices
            ])

            return render_template(
                "watch_detail.html",
                watch=watch,
                watch_type=watch_type,
                title=title,
                prices=prices,
                prices_json=prices_json,
            )
        finally:
            session.close()

    @app.route("/watches/<watch_type>/<int:watch_id>/update", methods=["POST"])
    def update_watch(watch_type, watch_id):
        session = SessionLocal()
        try:
            if watch_type == "flight":
                watch = session.query(FlightWatch).get(watch_id)
            elif watch_type == "hotel":
                watch = session.query(HotelWatch).get(watch_id)
            else:
                return "Invalid watch type", 404

            if not watch:
                return "Watch not found", 404

            threshold = request.form.get("threshold_price")
            watch.threshold_price = float(threshold) if threshold else None
            session.commit()
            flash("Threshold updated!", "success")
            return redirect(url_for("watch_detail", watch_type=watch_type, watch_id=watch_id))
        finally:
            session.close()

    @app.route("/status")
    def status_page():
        session = SessionLocal()
        try:
            flights = session.query(FlightWatch).filter_by(is_active=True).all()
            hotels = session.query(HotelWatch).filter_by(is_active=True).all()

            watch_statuses = []
            for w in flights:
                latest = (
                    session.query(PriceRecord)
                    .filter_by(watch_type="flight", watch_id=w.id)
                    .order_by(PriceRecord.scraped_at.desc())
                    .first()
                )
                count = session.query(PriceRecord).filter_by(watch_type="flight", watch_id=w.id).count()
                watch_statuses.append({
                    "type": "Flight",
                    "name": f"{w.origin} -> {w.destination}",
                    "last_check": latest.scraped_at if latest else None,
                    "last_price": f"{latest.currency} {latest.price:.0f}" if latest else None,
                    "total_records": count,
                })

            for w in hotels:
                latest = (
                    session.query(PriceRecord)
                    .filter_by(watch_type="hotel", watch_id=w.id)
                    .order_by(PriceRecord.scraped_at.desc())
                    .first()
                )
                count = session.query(PriceRecord).filter_by(watch_type="hotel", watch_id=w.id).count()
                watch_statuses.append({
                    "type": "Hotel",
                    "name": w.hotel_name,
                    "last_check": latest.scraped_at if latest else None,
                    "last_price": f"{latest.currency} {latest.price:.0f}" if latest else None,
                    "total_records": count,
                })

            serpapi_configured = bool(Config.SERPAPI_KEY)
            telegram_configured = bool(Config.TELEGRAM_BOT_TOKEN and Config.TELEGRAM_CHAT_ID)

            return render_template("status.html",
                                   watches=watch_statuses,
                                   serpapi_configured=serpapi_configured,
                                   telegram_configured=telegram_configured,
                                   interval=Config.SCRAPE_INTERVAL_HOURS,
                                   max_watches=Config.MAX_WATCHES)
        finally:
            session.close()

    return app


def start_scheduler():
    from scheduler.jobs import check_all_watches, cleanup_old_prices

    scheduler = BackgroundScheduler()
    interval = Config.SCRAPE_INTERVAL_HOURS

    scheduler.add_job(check_all_watches, "interval", hours=interval, id="check_all",
                      next_run_time=datetime.now())
    scheduler.add_job(cleanup_old_prices, "cron", hour=3, id="cleanup")

    scheduler.start()
    logger.info(f"Scheduler started: checking prices every {interval}h (twice daily). First check NOW.")
    return scheduler


if __name__ == "__main__":
    app = create_app()
    scheduler = start_scheduler()

    try:
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port, debug=False)
    finally:
        scheduler.shutdown()
