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


class SkyscannerFlightScraper(BaseScraper):
    SCRAPER_NAME = "skyscanner_flights"

    SELECTORS = {
        "result_item": "div[class*='FlightsResults'], div[class*='BpkTicket'], a[class*='day-view-item']",
        "price": "span[class*='price'], span[class*='Price'], div[class*='price'] span",
        "airline": "span[class*='carrier'], span[class*='Carrier'], img[alt]",
        "duration": "span[class*='duration'], span[class*='Duration']",
        "stops": "span[class*='stops'], span[class*='Stops']",
    }

    def _build_url(self, origin: str, destination: str, departure_date: str, return_date: str | None) -> str:
        # Skyscanner URL pattern: /transport/flights/IATA/IATA/YYMMDD/
        dep = departure_date[2:].replace("-", "")  # "2026-04-15" -> "260415"
        base = f"https://www.skyscanner.com/transport/flights/{origin.lower()}/{destination.lower()}/{dep}/"
        if return_date:
            ret = return_date[2:].replace("-", "")
            base += f"{ret}/"
        return base

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
            await random_delay(3.0, 8.0)  # Skyscanner is more aggressive with bot detection
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await random_delay(5.0, 10.0)

            # Wait for results
            try:
                await page.wait_for_selector(
                    self.SELECTORS["result_item"], timeout=25000
                )
            except Exception:
                logger.warning(f"[{self.SCRAPER_NAME}] No results found, saving debug screenshot")
                await save_debug_screenshot(page, self.SCRAPER_NAME)
                return []

            items = await page.query_selector_all(self.SELECTORS["result_item"])
            logger.info(f"[{self.SCRAPER_NAME}] Found {len(items)} flight items")

            for item in items[:10]:
                try:
                    price_el = await item.query_selector(self.SELECTORS["price"])
                    if not price_el:
                        continue

                    price_text = await price_el.inner_text()
                    price = parse_price(price_text)
                    if price is None or not validate_price(price):
                        continue

                    details = {}
                    for key in ["airline", "duration", "stops"]:
                        el = await item.query_selector(self.SELECTORS[key])
                        if el:
                            text = await el.inner_text()
                            if text:
                                details[key] = text.strip()

                    results.append(
                        PriceResult(
                            price=price,
                            currency="USD",
                            source="skyscanner",
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
        raise NotImplementedError("Skyscanner scraper only supports flights")
