import logging
from datetime import datetime

import httpx

from config import Config
from scrapers.base import PriceResult

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"


def search_flights(origin: str, destination: str, departure_date: str, return_date: str | None,
                   currency: str = "USD") -> list[PriceResult]:
    """Search Google Flights via SerpAPI. Returns list of PriceResult."""
    params = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": departure_date,
        "currency": currency,
        "hl": "en",
        "api_key": Config.SERPAPI_KEY,
    }
    if return_date:
        params["return_date"] = return_date
        params["type"] = "1"  # round trip
    else:
        params["type"] = "2"  # one way

    logger.info(f"[google_flights] Searching {origin} -> {destination} on {departure_date} ({currency})")

    try:
        resp = httpx.get(SERPAPI_URL, params=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"[google_flights] API request failed: {e}")
        raise

    results = []

    # Build Google Flights search URL for booking link
    booking_url = f"https://www.google.com/travel/flights?q=Flights%20to%20{destination}%20from%20{origin}%20on%20{departure_date}"
    if return_date:
        booking_url += f"%20return%20{return_date}"

    for category in ["best_flights", "other_flights"]:
        for flight in data.get(category, []):
            price = flight.get("price")
            if not price or not isinstance(price, (int, float)):
                continue

            legs = flight.get("flights", [])

            # Build detailed source label: "Airline (Flight#, Stops)"
            airlines = []
            flight_numbers = []
            for leg in legs:
                airline = leg.get("airline", "")
                fn = leg.get("flight_number", "")
                if airline and airline not in airlines:
                    airlines.append(airline)
                if fn:
                    flight_numbers.append(fn)

            airline_str = " + ".join(airlines) if airlines else "Unknown"
            stops = len(legs) - 1
            stops_str = "Direct" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"

            # Source shows airline and stops
            source = f"{airline_str} ({stops_str})"

            details = {
                "type": category.replace("_", " "),
                "airline": airline_str,
                "flight_numbers": ", ".join(flight_numbers),
                "stops": stops,
                "stops_label": stops_str,
                "total_duration": flight.get("total_duration"),
                "booking_url": booking_url,
            }

            if legs:
                details["departure_time"] = legs[0].get("departure_airport", {}).get("time")
                details["arrival_time"] = legs[-1].get("arrival_airport", {}).get("time")
                details["departure_airport"] = legs[0].get("departure_airport", {}).get("name")
                details["arrival_airport"] = legs[-1].get("arrival_airport", {}).get("name")

            # Format duration
            duration_min = flight.get("total_duration")
            if duration_min:
                hours, mins = divmod(duration_min, 60)
                details["duration_label"] = f"{hours}h {mins}m"

            results.append(PriceResult(
                price=float(price),
                currency=currency,
                source=source,
                raw_details=details,
            ))

    logger.info(f"[google_flights] Found {len(results)} flight options")
    return results
