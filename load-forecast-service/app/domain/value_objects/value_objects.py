"""
Value Objects — Load Forecast Bounded Context.

Alle value objects er immutable (frozen dataclasses).
Navne matcher Ubiquitous Language præcist.

Dette bounded context må ALDRIG importere fra charging-session-service.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimeFeature:
    """
    Tidsbaseret feature brugt som input til ForecastModel.

    Felter:
        hour_of_day:  time på dagen (0–23)
        day_of_week:  ugedag (1 = mandag, 7 = søndag)

    Invarianter:
        0 ≤ hour_of_day ≤ 23
        1 ≤ day_of_week ≤ 7

    Event Storming: bruges som feature-vektor i 'Generer Prognose'-use case.
    """
    hour_of_day: int
    day_of_week: int

    def __post_init__(self) -> None:
        if not (0 <= self.hour_of_day <= 23):
            raise ValueError(
                f"hour_of_day skal være 0–23, fik: {self.hour_of_day}"
            )
        if not (1 <= self.day_of_week <= 7):
            raise ValueError(
                f"day_of_week skal være 1–7, fik: {self.day_of_week}"
            )


@dataclass(frozen=True)
class PriceFeatures:
    """
    Prisbaseret feature fra energimarkedet brugt som input til ForecastModel.

    Felter:
        spot_price: spotpris i DKK/kWh fra energimarkedet

    Event Storming: repræsenterer markedsprissignal i 'Generer Prognose'.
    """
    spot_price: float  # DKK/kWh


@dataclass(frozen=True)
class SessionCount:
    """
    Historisk antal afsluttede opladningssessioner ved samme tid og ugedag.
    Bruges som target-variabel og som historisk feature i ML-modellen.

    Invariant: SessionCount ≥ 0 — aldrig negativ.

    Event Storming: aggregeret historisk session-volumen fra charging-session-service.
    """
    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError(
                f"SessionCount kan ikke være negativ, fik: {self.value}"
            )
