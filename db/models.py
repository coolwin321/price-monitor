from datetime import datetime, date

from sqlalchemy import (
    Integer,
    String,
    Float,
    Boolean,
    Date,
    DateTime,
    Text,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class FlightWatch(Base):
    __tablename__ = "flight_watches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    origin: Mapped[str] = mapped_column(String(10), nullable=False)
    destination: Mapped[str] = mapped_column(String(10), nullable=False)
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    threshold_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self):
        return {
            "id": self.id,
            "origin": self.origin,
            "destination": self.destination,
            "departure_date": self.departure_date.isoformat(),
            "return_date": self.return_date.isoformat() if self.return_date else None,
            "threshold_price": self.threshold_price,
            "currency": self.currency,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }


class HotelWatch(Base):
    __tablename__ = "hotel_watches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    checkin_date: Mapped[date] = mapped_column(Date, nullable=False)
    checkout_date: Mapped[date] = mapped_column(Date, nullable=False)
    threshold_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self):
        return {
            "id": self.id,
            "hotel_name": self.hotel_name,
            "location": self.location,
            "checkin_date": self.checkin_date.isoformat(),
            "checkout_date": self.checkout_date.isoformat(),
            "threshold_price": self.threshold_price,
            "currency": self.currency,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }


class PriceRecord(Base):
    __tablename__ = "price_records"
    __table_args__ = (
        Index("ix_price_lookup", "watch_type", "watch_id", "scraped_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watch_type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'flight' or 'hotel'
    watch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    raw_details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AlertSent(Base):
    __tablename__ = "alerts_sent"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watch_type: Mapped[str] = mapped_column(String(10), nullable=False)
    watch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ScraperHealth(Base):
    __tablename__ = "scraper_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scraper_name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
