import json
import logging

from scrapers.base import BaseScraper, PriceResult
from scrapers.utils import (
    get_random_ua,
    get_random_viewport,
    random_delay,
    mark_scraped,
    validate_price,
    parse_price,
    save_debug_screenshot,
    retry_scrape,
)

logger = logging.getLogger(__name__)


class TripFlightScraper(BaseScraper):
    SCRAPER_NAME = "trip_flights"

    SELECTORS = {
        "result_list": "div[class*='flight-list'], div[class*='FlightList']",
        "result_item": "div[class*='flight-item'], div[class*='FlightItem'], div[class*='list-item']",
        "price": "span[class*='price'], div[class*='price'] span, [class*='Price']",
        "airline": "span[class*='airline'], div[class*='airline'], [class*='Airline']",
        "duration": "span[class*='duration'], div[class*='duration'], [class*='Duration']",
        "stops": "span[class*='stop'], div[class*='stop'], [class*='Stop']",
    }

    def _build_url(self, origin: str, destination: str, departure_date: str, return_date: str | None) -> str:
        # Trip.com flight search URL pattern
        base = "https://www.trip.com/flights"
        dep = departure_date.replace("-", "")
        if return_date:
            ret = return_date.replace("-", "")
            return f"{base}/{origin.lower()}-to-{destination.lower()}/tickets-{origin.lower()}-{destination.lower()}?dcity={origin}&acity={destination}&ddate={departure_date}&rdate={return_date}&flighttype=rt"
        return f"{base}/{origin.lower()}-to-{destination.lower()}/tickets-{origin.lower()}-{destination.lower()}?dcity={origin}&acity={destination}&ddate={departure_date}&flighttype=ow"

    @retry_scrape(max_retries=2, backoff_base=30)
    async def scrape_flight(
        self, origin: str, destination: str, departure_date: str, return_date: str | None,
        browser_context=None,
    ) -> list[PriceResult]:
        if browser_context is None:
            raise ValueError("browser_context is required")

        url = self._build_url(origin, destination, departure_date, return_date)
        logger.info(f"[{self.SCRAPER_NAME}] Scraping: {url}")

        page = await browser_context.new_page()
        results = []

        try:
            await random_delay(2.0, 5.0)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await random_delay(3.0, 8.0)

            # Wait for flight results to load
            try:
                await page.wait_for_selector(
                    self.SELECTORS["result_item"], timeout=20000
                )
            except Exception:
                logger.warning(f"[{self.SCRAPER_NAME}] No results found, saving debug screenshot")
                await save_debug_screenshot(page, self.SCRAPER_NAME)
                return []

            items = await page.query_selector_all(self.SELECTORS["result_item"])
            logger.info(f"[{self.SCRAPER_NAME}] Found {len(items)} flight items")

            for item in items[:10]:  # Limit to top 10 results
                try:
                    price_el = await item.query_selector(self.SELECTORS["price"])
                    if not price_el:
                        continue

                    price_text = await price_el.inner_text()
                    price = parse_price(price_text)
                    if price is None or not validate_price(price):
                        continue

                    # Extract optional details
                    details = {}
                    for key in ["airline", "duration", "stops"]:
                        el = await item.query_selector(self.SELECTORS[key])
                        if el:
                            details[key] = (await el.inner_text()).strip()

                    results.append(
                        PriceResult(
                            price=price,
                            currency="USD",
                            source="trip.com",
                            raw_details=details,
                        )
                    )
                except Exception as e:
                    logger.debug(f"[{self.SCRAPER_NAME}] Error parsing item: {e}")
                    continue

            mark_scraped(self.SCRAPER_NAME)
            logger.info(f"[{self.SCRAPER_NAME}] Extracted {len(results)} prices")

        except Exception as e:
            logger.error(f"[{self.SCRAPER_NAME}] Scrape failed: {e}")
            await save_debug_screenshot(page, self.SCRAPER_NAME)
            raise
        finally:
            await page.close()

        return results

    async def scrape_hotel(self, hotel_name, location, checkin, checkout):
        raise NotImplementedError("Use TripHotelScraper for hotels")
