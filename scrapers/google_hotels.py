import logging
from datetime import datetime

import httpx

from config import Config
from scrapers.base import PriceResult

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"


def search_hotels(hotel_name: str, location: str, checkin: str, checkout: str) -> list[PriceResult]:
    """Search Google Hotels via SerpAPI. Returns list of PriceResult."""
    query = f"{hotel_name} {location}"

    params = {
        "engine": "google_hotels",
        "q": query,
        "check_in_date": checkin,
        "check_out_date": checkout,
        "currency": "USD",
        "hl": "en",
        "api_key": Config.SERPAPI_KEY,
    }

    logger.info(f"[google_hotels] Searching '{query}' {checkin} → {checkout}")

    try:
        resp = httpx.get(SERPAPI_URL, params=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"[google_hotels] API request failed: {e}")
        raise

    results = []

    for prop in data.get("properties", []):
        # Get the rate per night
        rate_info = prop.get("rate_per_night", {})
        price_str = rate_info.get("lowest")
        if not price_str:
            # Try extracted_lowest as fallback
            price = rate_info.get("extracted_lowest")
        else:
            # Parse "$123" style string
            price = _parse_price(price_str)

        if not price:
            continue

        details = {
            "hotel_name": prop.get("name"),
            "rating": prop.get("overall_rating"),
            "reviews": prop.get("reviews"),
            "hotel_class": prop.get("hotel_class"),
            "amenities": prop.get("amenities", [])[:5],  # first 5 amenities
            "check_in_time": prop.get("check_in_time"),
            "check_out_time": prop.get("check_out_time"),
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
            currency="USD",
            source="google_hotels",
            raw_details=details,
        ))

    logger.info(f"[google_hotels] Found {len(results)} hotel options")
    return results


def _parse_price(text: str) -> float | None:
    """Parse price string like '$123' or '¥15,000'."""
    cleaned = text.strip()
    for char in ["$", "€", "£", "¥", "₹", ",", " ", "\xa0"]:
        cleaned = cleaned.replace(char, "")
    try:
        return float(cleaned)
    except ValueError:
        return None
