import logging
from datetime import datetime

import httpx

from config import Config
from scrapers.base import PriceResult

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"


def search_flights(origin: str, destination: str, departure_date: str, return_date: str | None) -> list[PriceResult]:
    """Search Google Flights via SerpAPI. Returns list of PriceResult."""
    params = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": departure_date,
        "currency": "USD",
        "hl": "en",
        "api_key": Config.SERPAPI_KEY,
    }
    if return_date:
        params["return_date"] = return_date
        params["type"] = "1"  # round trip
    else:
        params["type"] = "2"  # one way

    logger.info(f"[google_flights] Searching {origin} → {destination} on {departure_date}")

    try:
        resp = httpx.get(SERPAPI_URL, params=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"[google_flights] API request failed: {e}")
        raise

    results = []

    # Parse best flights
    for category in ["best_flights", "other_flights"]:
        for flight in data.get(category, []):
            price = flight.get("price")
            if not price or not isinstance(price, (int, float)):
                continue

            # Extract flight details
            legs = flight.get("flights", [])
            details = {
                "type": category.replace("_", " "),
                "stops": len(legs) - 1,
                "total_duration": flight.get("total_duration"),
            }
            if legs:
                first_leg = legs[0]
                details["airline"] = first_leg.get("airline")
                details["departure_time"] = first_leg.get("departure_airport", {}).get("time")
                details["arrival_time"] = legs[-1].get("arrival_airport", {}).get("time")
                details["flight_number"] = first_leg.get("flight_number")

            results.append(PriceResult(
                price=float(price),
                currency="USD",
                source="google_flights",
                raw_details=details,
            ))

    logger.info(f"[google_flights] Found {len(results)} flight options")
    return results
