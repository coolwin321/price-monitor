import logging
from datetime import datetime

import httpx

from config import Config
from scrapers.base import PriceResult

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"


def search_hotels(hotel_name: str, location: str, checkin: str, checkout: str,
                  currency: str = "USD") -> list[PriceResult]:
    """Search Google Hotels via SerpAPI. Returns list of PriceResult."""
    query = f"{hotel_name} {location}"

    params = {
        "engine": "google_hotels",
        "q": query,
        "check_in_date": checkin,
        "check_out_date": checkout,
        "currency": currency,
        "hl": "en",
        "api_key": Config.SERPAPI_KEY,
    }

    logger.info(f"[google_hotels] Searching '{query}' {checkin} -> {checkout} ({currency})")

    try:
        resp = httpx.get(SERPAPI_URL, params=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"[google_hotels] API request failed: {e}")
        raise

    results = []

    for prop in data.get("properties", []):
        rate_info = prop.get("rate_per_night", {})
        price_str = rate_info.get("lowest")
        if not price_str:
            price = rate_info.get("extracted_lowest")
        else:
            price = _parse_price(price_str)

        if not price:
            continue

        hotel_display_name = prop.get("name", hotel_name)
        source = hotel_display_name

        # Build Google Hotels link
        from urllib.parse import quote
        booking_url = f"https://www.google.com/travel/hotels?q={quote(query)}&dates={checkin},{checkout}"

        details = {
            "hotel_name": hotel_display_name,
            "rating": prop.get("overall_rating"),
            "reviews": prop.get("reviews"),
            "hotel_class": prop.get("hotel_class"),
            "amenities": prop.get("amenities", [])[:5],
            "booking_url": booking_url,
        }

        # Get total price if available
        total_info = prop.get("total_rate", {})
        if total_info.get("extracted_lowest"):
            details["total_price"] = total_info["extracted_lowest"]

        # Get nearby places
        nearby = prop.get("nearby_places", [])
        if nearby:
            details["nearby"] = [p.get("name") for p in nearby[:3]]

        results.append(PriceResult(
            price=float(price),
            currency=currency,
            source=source,
            raw_details=details,
        ))

    logger.info(f"[google_hotels] Found {len(results)} hotel options")
    return results


def _parse_price(text: str) -> float | None:
    """Parse price string like '$123' or '¥15,000'."""
    cleaned = text.strip()
    for char in ["$", "€", "£", "¥", "₹", "HK$", ",", " ", "\xa0"]:
        cleaned = cleaned.replace(char, "")
    try:
        return float(cleaned)
    except ValueError:
        return None
