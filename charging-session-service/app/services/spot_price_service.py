"""
Integration med Energidataservice (Energinet) til day-ahead spotpriser.

Prisen hentes ved sessionstart og låses på sessionen.
Sidst kendte pris gemmes som fallback hvis API er nede.
"""
import logging
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Fallback: gemmer sidst kendte pris per priszone
_LAST_KNOWN_PRICE: dict[str, float] = {}


def get_spot_price(price_area: str, session_start_time: datetime, base_url: str) -> float:
    """
    Henter spotpris for den time session_start_time falder inden for.
    Konverterer DKK/MWh → DKK/kWh (divider med 1000).
    Returnerer fallback-pris hvis API er utilgængeligt.
    """
    try:
        params = {
            "filter": f'{{"PriceArea":["{price_area}"]}}',
            "sort": "TimeDK desc",
            "limit": 24,
        }
        response = requests.get(base_url, params=params, timeout=5)
        response.raise_for_status()

        records = response.json().get("records", [])
        session_hour = session_start_time.replace(minute=0, second=0, microsecond=0)

        for record in records:
            try:
                record_time = datetime.fromisoformat(record.get("TimeDK", ""))
                price_dkk = record.get("SpotPriceDKK")
                if record_time == session_hour and price_dkk is not None:
                    price_kwh = price_dkk / 1000.0
                    _LAST_KNOWN_PRICE[price_area] = price_kwh
                    logger.info(
                        "Spotpris %s kl. %s: %.4f DKK/kWh",
                        price_area, session_hour, price_kwh
                    )
                    return price_kwh
            except (ValueError, KeyError) as e:
                logger.debug("Fejl ved behandling af record: %s", e)
                continue

        # Ingen eksakt time-match — brug første tilgængelige post
        if records:
            first_record = records[0]
            price_dkk = first_record.get("SpotPriceDKK")
            if price_dkk is not None:
                price_kwh = price_dkk / 1000.0
                _LAST_KNOWN_PRICE[price_area] = price_kwh
                logger.warning(
                    "Ingen eksakt match for %s, bruger første post: %.4f DKK/kWh",
                    session_hour, price_kwh
                )
                return price_kwh
            else:
                logger.error("Første record mangler 'SpotPriceDKK'")

    except requests.RequestException as exc:
        logger.error("Energidataservice utilgængeligt: %s", exc)

    # Fallback til sidst kendte pris (default 0.50 DKK/kWh)
    fallback = _LAST_KNOWN_PRICE.get(price_area, 0.50)
    logger.warning("Bruger fallback pris for %s: %.4f DKK/kWh", price_area, fallback)
    return fallback
