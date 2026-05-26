"""
Energy Price Integration Bounded Context — ekstern adapter.

Dette bounded context lever INDE I charging-session-service som ekstern adapter,
da det udelukkende servicerer ChargingSession-aggregatet.
Det må ALDRIG importeres af load-forecast-service.

Aggregat-rod: SpotPriceRecord
Value Objects: PriceArea, CalculatedSpotPrice

Infrastruktur: SpotPriceClient henter spotpriser fra Energidataservice.
API: https://api.energidataservice.dk/dataset/DayAheadPrices?limit=5
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Value Objects — Energy Price Integration BC
# ---------------------------------------------------------------------------

class PriceArea(Enum):
    """
    Dansk elpriszone.
    Invariant: PriceArea ∈ {DK1, DK2} — ingen andre værdier tilladt.

    Event Storming: bruges ved opslag af spotpris ved SESSION_AUTHORIZED.
    """
    DK1 = "DK1"
    DK2 = "DK2"


@dataclass(frozen=True)
class CalculatedSpotPrice:
    """
    Beregnet spotpris fra Energidataservice (DKK/kWh).
    Invariant: CalculatedSpotPrice ≥ 0 — aldrig negativ.

    Konverteres til AppliedSpotPrice og låses på ChargingSession ved SESSION_AUTHORIZED.
    """
    value: float  # DKK pr. kWh

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError(
                f"CalculatedSpotPrice kan ikke være negativ, fik: {self.value}"
            )

    def __str__(self) -> str:
        return f"{self.value:.4f} DKK/kWh"


# ---------------------------------------------------------------------------
# Aggregat-rod — Energy Price Integration BC
# ---------------------------------------------------------------------------

@dataclass
class SpotPriceRecord:
    """
    Aggregat-rod for Energy Price Integration Bounded Context.
    Repræsenterer en konkret spotpris-post hentet fra Energidataservice.

    Felter:
        price_area:            DK1 eller DK2
        calculated_spot_price: spotpris i DKK/kWh (aldrig negativ)
        hour_dk:               tidspunkt for prisperioden
        fetched_at:            hvornår posten blev hentet

    Anti-korruption: to_applied_spot_price() udstiller prisen som en ren float,
    så Charging Session BC kan oprette sin AppliedSpotPrice value object
    uden at importere noget fra dette bounded context.

    Event Storming: bruges som input til 'Autoriser Session'-kommandoen.
    """
    price_area: PriceArea
    calculated_spot_price: CalculatedSpotPrice
    hour_dk: datetime
    fetched_at: datetime

    def to_applied_spot_price(self) -> float:
        """
        Returnerer CalculatedSpotPrice som en ren float-værdi.

        Anti-korruptionslag: Charging Session BC opretter sin AppliedSpotPrice
        value object ud fra denne float — der sker ingen direkte import
        på tværs af bounded contexts.

        Returns:
            float — spotpris i DKK/kWh, aldrig negativ.
        """
        return self.calculated_spot_price.value


# ---------------------------------------------------------------------------
# Infrastruktur-adapter
# ---------------------------------------------------------------------------

_ENERGIDATA_URL = (
    "https://api.energidataservice.dk/dataset/DayAheadPrices"
    "?limit=5&sort=HourDK desc"
)

# Fallback-pris brugt ved API-fejl (gennemsnitlig dansk spotpris DKK/kWh)
_FALLBACK_SPOT_PRICE_DKK_PER_KWH = 1.25


class SpotPriceClient:
    """
    Ekstern adapter der henter aktuelle spotpriser fra Energidataservice.
    Returnerer altid et SpotPriceRecord — ved fejl bruges en fallback-pris.

    Energidataservice API:
        GET https://api.energidataservice.dk/dataset/DayAheadPrices?limit=5

    Response-feltnavne (DK): HourDK, SpotPriceDKK, PriceArea
    SpotPriceDKK er i MWh → konverteres til kWh ved division med 1000.
    """

    def __init__(self, timeout_sekunder: int = 5) -> None:
        self._timeout = timeout_sekunder

    def hent_aktuel_pris(self, price_area: PriceArea) -> SpotPriceRecord:
        """
        Henter den seneste spotpris for den givne priszone.

        Args:
            price_area: DK1 eller DK2

        Returns:
            SpotPriceRecord med CalculatedSpotPrice i DKK/kWh

        Ved netværksfejl eller ugyldigt svar returneres fallback-pris.

        Event Storming: kaldt af 'Autoriser Session'-use case.
        """
        try:
            url = f"{_ENERGIDATA_URL}&filter={{\"PriceArea\":\"{price_area.value}\"}}"
            response = requests.get(url, timeout=self._timeout)
            response.raise_for_status()
            data = response.json()

            records = data.get("records", [])
            if not records:
                logger.warning(
                    "Ingen spotpris-records fra Energidataservice for %s — bruger fallback",
                    price_area.value,
                )
                return self._fallback(price_area)

            # Hent den seneste record
            record = records[0]
            spot_price_mwh: Optional[float] = record.get("SpotPriceDKK")

            if spot_price_mwh is None:
                logger.warning("SpotPriceDKK mangler i response — bruger fallback")
                return self._fallback(price_area)

            # Energidataservice returnerer DKK/MWh → konverter til DKK/kWh
            spot_price_kwh = max(spot_price_mwh / 1000.0, 0.0)

            hour_dk_str: str = record.get("HourDK", "")
            try:
                hour_dk = datetime.fromisoformat(hour_dk_str)
            except (ValueError, TypeError):
                hour_dk = datetime.utcnow()

            return SpotPriceRecord(
                price_area=price_area,
                calculated_spot_price=CalculatedSpotPrice(value=round(spot_price_kwh, 6)),
                hour_dk=hour_dk,
                fetched_at=datetime.utcnow(),
            )

        except requests.RequestException as exc:
            logger.error(
                "Fejl ved hentning af spotpris fra Energidataservice: %s — bruger fallback",
                exc,
            )
            return self._fallback(price_area)

    # ------------------------------------------------------------------
    # Privat hjælpemetode
    # ------------------------------------------------------------------

    def _fallback(self, price_area: PriceArea) -> SpotPriceRecord:
        """Returnerer en SpotPriceRecord med fallback-pris ved API-fejl."""
        return SpotPriceRecord(
            price_area=price_area,
            calculated_spot_price=CalculatedSpotPrice(value=_FALLBACK_SPOT_PRICE_DKK_PER_KWH),
            hour_dk=datetime.utcnow(),
            fetched_at=datetime.utcnow(),
        )
