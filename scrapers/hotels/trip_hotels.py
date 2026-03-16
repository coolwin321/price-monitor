import logging

from scrapers.base import BaseScraper, PriceResult
from scrapers.utils import (
    random_delay,
    mark_scraped,
    validate_price,
    parse_price,
    save_debug_screenshot,
    retry_scrape,
)

logger = logging.getLogger(__name__)


class TripHotelScraper(BaseScraper):
    SCRAPER_NAME = "trip_hotels"

    SELECTORS = {
        "result_item": "div[class*='hotel-item'], div[class*='HotelItem'], div[class*='list-card']",
        "price": "span[class*='price'], div[class*='price'] span, [class*='Price']",
        "hotel_name": "span[class*='hotel-name'], div[class*='name'], h3, [class*='HotelName']",
        "rating": "span[class*='score'], span[class*='rating'], [class*='Score']",
        "star": "span[class*='star'], [class*='Star']",
    }

    def _build_url(self, hotel_name: str, location: str, checkin: str, checkout: str) -> str:
        from urllib.parse import quote
        query = quote(f"{hotel_name} {location}")
        return (
            f"https://www.trip.com/hotels/list?"
            f"city=0&keyword={query}"
            f"&checkin={checkin}&checkout={checkout}"
        )

    @retry_scrape(max_retries=2, backoff_base=30)
    async def scrape_hotel(
        self, hotel_name: str, location: str, checkin: str, checkout: str,
        browser_context=None,
    ) -> list[PriceResult]:
        if browser_context is None:
            raise ValueError("browser_context is required")

        url = self._build_url(hotel_name, location, checkin, checkout)
        logger.info(f"[{self.SCRAPER_NAME}] Scraping: {url}")

        page = await browser_context.new_page()
        results = []

        try:
            await random_delay(2.0, 5.0)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await random_delay(3.0, 8.0)

            try:
                await page.wait_for_selector(
                    self.SELECTORS["result_item"], timeout=20000
                )
            except Exception:
                logger.warning(f"[{self.SCRAPER_NAME}] No results found")
                await save_debug_screenshot(page, self.SCRAPER_NAME)
                return []

            items = await page.query_selector_all(self.SELECTORS["result_item"])
            logger.info(f"[{self.SCRAPER_NAME}] Found {len(items)} hotel items")

            for item in items[:10]:
                try:
                    price_el = await item.query_selector(self.SELECTORS["price"])
                    if not price_el:
                        continue

                    price_text = await price_el.inner_text()
                    price = parse_price(price_text)
                    if price is None or not validate_price(price, min_price=1.0, max_price=10000.0):
                        continue

                    details = {}
                    for key in ["hotel_name", "rating", "star"]:
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

    async def scrape_flight(self, origin, destination, departure_date, return_date):
        raise NotImplementedError("Use TripFlightScraper for flights")
