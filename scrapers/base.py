from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PriceResult:
    price: float
    currency: str
    source: str
    raw_details: dict = field(default_factory=dict)
    scraped_at: datetime = field(default_factory=datetime.utcnow)


class BaseScraper(ABC):
    SCRAPER_NAME: str = "base"

    @abstractmethod
    async def scrape_flight(
        self, origin: str, destination: str, departure_date: str, return_date: str | None
    ) -> list[PriceResult]:
        raise NotImplementedError

    @abstractmethod
    async def scrape_hotel(
        self, hotel_name: str, location: str, checkin: str, checkout: str
    ) -> list[PriceResult]:
        raise NotImplementedError
