"""
SpotPriceClient: adapter til Energidataservice (Energinet) day-ahead spotpriser.

Konverterer DKK/MWh → DKK/kWh og returnerer en SpotPrice value object.
Sidst kendte pris per priszone gemmes som fallback hvis API er nede.
"""
import logging
from datetime import datetime

import requests

from app.domain.value_objects import SpotPrice

logger = logging.getLogger(__name__)

_DEFAULT_FALLBACK_DKK_PER_KWH = 0.50


class SpotPriceClient:
    def __init__(self, base_url: str):
        self._base_url = base_url
        self._cache: dict[str, float] = {}

    def fetch(self, price_area: str, at: datetime) -> SpotPrice:
        """Henter spotpris for det givne tidspunkt og priszone."""
        dkk_per_kwh = self._fetch_from_api(price_area, at)
        return SpotPrice(price_area=price_area, dkk_per_kwh=dkk_per_kwh)

    def _fetch_from_api(self, price_area: str, at: datetime) -> float:
        try:
            params = {
                "filter": f'{{"PriceArea":["{price_area}"]}}',
                "sort": "TimeDK desc",
                "limit": 24,
            }
            response = requests.get(self._base_url, params=params, timeout=5)
            response.raise_for_status()

            records = response.json().get("records", [])
            session_hour = at.replace(minute=0, second=0, microsecond=0)

            for record in records:
                try:
                    record_time = datetime.fromisoformat(record.get("TimeDK", ""))
                    price_dkk = record.get("SpotPriceDKK")
                    if record_time == session_hour and price_dkk is not None:
                        price_kwh = price_dkk / 1000.0
                        self._cache[price_area] = price_kwh
                        logger.info("Spotpris %s kl. %s: %.4f DKK/kWh", price_area, session_hour, price_kwh)
                        return price_kwh
                except (ValueError, KeyError) as e:
                    logger.debug("Fejl ved behandling af record: %s", e)
                    continue

            if records:
                price_dkk = records[0].get("SpotPriceDKK")
                if price_dkk is not None:
                    price_kwh = price_dkk / 1000.0
                    self._cache[price_area] = price_kwh
                    logger.warning("Ingen eksakt match for %s, bruger første post: %.4f DKK/kWh", session_hour, price_kwh)
                    return price_kwh

        except requests.RequestException as exc:
            logger.error("Energidataservice utilgængeligt: %s", exc)

        fallback = self._cache.get(price_area, _DEFAULT_FALLBACK_DKK_PER_KWH)
        logger.warning("Bruger fallback pris for %s: %.4f DKK/kWh", price_area, fallback)
        return fallback
