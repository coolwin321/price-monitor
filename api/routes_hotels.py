from datetime import datetime

from flask import Blueprint, jsonify, request

from db.database import SessionLocal
from db.models import HotelWatch, PriceRecord

hotels_bp = Blueprint("hotels", __name__, url_prefix="/api/hotels")


@hotels_bp.route("", methods=["GET"])
def list_hotels():
    session = SessionLocal()
    try:
        watches = session.query(HotelWatch).order_by(HotelWatch.created_at.desc()).all()
        return jsonify([w.to_dict() for w in watches])
    finally:
        session.close()


@hotels_bp.route("", methods=["POST"])
def create_hotel():
    data = request.json
    session = SessionLocal()
    try:
        watch = HotelWatch(
            hotel_name=data["hotel_name"],
            location=data["location"],
            checkin_date=datetime.strptime(data["checkin_date"], "%Y-%m-%d").date(),
            checkout_date=datetime.strptime(data["checkout_date"], "%Y-%m-%d").date(),
            threshold_price=data.get("threshold_price"),
            currency=data.get("currency", "USD"),
        )
        session.add(watch)
        session.commit()
        session.refresh(watch)
        return jsonify(watch.to_dict()), 201
    finally:
        session.close()


@hotels_bp.route("/<int:watch_id>", methods=["GET"])
def get_hotel(watch_id):
    session = SessionLocal()
    try:
        watch = session.query(HotelWatch).get(watch_id)
        if not watch:
            return jsonify({"error": "Not found"}), 404

        result = watch.to_dict()
        latest_prices = (
            session.query(PriceRecord)
            .filter_by(watch_type="hotel", watch_id=watch_id)
            .order_by(PriceRecord.scraped_at.desc())
            .limit(20)
            .all()
        )
        result["latest_prices"] = [
            {
                "source": p.source,
                "price": p.price,
                "currency": p.currency,
                "scraped_at": p.scraped_at.isoformat(),
            }
            for p in latest_prices
        ]
        return jsonify(result)
    finally:
        session.close()


@hotels_bp.route("/<int:watch_id>", methods=["PUT"])
def update_hotel(watch_id):
    data = request.json
    session = SessionLocal()
    try:
        watch = session.query(HotelWatch).get(watch_id)
        if not watch:
            return jsonify({"error": "Not found"}), 404

        if "threshold_price" in data:
            watch.threshold_price = data["threshold_price"]
        if "is_active" in data:
            watch.is_active = data["is_active"]
        if "currency" in data:
            watch.currency = data["currency"]

        session.commit()
        session.refresh(watch)
        return jsonify(watch.to_dict())
    finally:
        session.close()


@hotels_bp.route("/<int:watch_id>", methods=["DELETE"])
def delete_hotel(watch_id):
    session = SessionLocal()
    try:
        watch = session.query(HotelWatch).get(watch_id)
        if not watch:
            return jsonify({"error": "Not found"}), 404
        watch.is_active = False
        session.commit()
        return jsonify({"status": "deactivated"})
    finally:
        session.close()


@hotels_bp.route("/<int:watch_id>/prices", methods=["GET"])
def get_hotel_prices(watch_id):
    session = SessionLocal()
    try:
        days = request.args.get("days", 30, type=int)
        source = request.args.get("source")
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)
        query = (
            session.query(PriceRecord)
            .filter(
                PriceRecord.watch_type == "hotel",
                PriceRecord.watch_id == watch_id,
                PriceRecord.scraped_at >= cutoff,
            )
        )
        if source:
            query = query.filter(PriceRecord.source == source)

        records = query.order_by(PriceRecord.scraped_at).all()
        return jsonify([
            {
                "source": r.source,
                "price": r.price,
                "currency": r.currency,
                "scraped_at": r.scraped_at.isoformat(),
                "raw_details": r.raw_details,
            }
            for r in records
        ])
    finally:
        session.close()
