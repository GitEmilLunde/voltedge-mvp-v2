"""
Value Objects — Charging Session Bounded Context.

Alle value objects er immutable (frozen dataclasses).
Navne matcher Ubiquitous Language præcist — ingen oversættelser.

Event Storming reference: orange post-its i Charging Session BC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Enumerationer
# ---------------------------------------------------------------------------

class ChargerType(Enum):
    """
    Type af lader tilknyttet sessionen.
    Invariant: ChargerType ∈ {"Normal Charger", "Fast Charger"} — ingen andre værdier tilladt.

    Event Storming command: 'Opret Session' — ladertype vælges ved sessionoprettelse.
    """
    NORMAL_CHARGER = "Normal Charger"
    FAST_CHARGER = "Fast Charger"


class ErrorType(Enum):
    """
    Fejlklassifikation på et Event — kun sat ved UNEXPECTED_STOPPAGE.
    Invariant: ErrorType ∈ {POWER_LOSS, CONNECTOR_FAULT, NETWORK_ERROR,
                             OVERHEATING, UNKNOWN}.
    I alle andre tilfælde er error_type None på Event-entiteten.

    Event Storming event: 'UNEXPECTED_STOPPAGE'.
    """
    POWER_LOSS       = "POWER_LOSS"
    CONNECTOR_FAULT  = "CONNECTOR_FAULT"
    NETWORK_ERROR    = "NETWORK_ERROR"
    OVERHEATING      = "OVERHEATING"
    UNKNOWN          = "UNKNOWN"


class ChargingStatus(Enum):
    """
    Statusklassifikation for en afsluttet ChargingSession.
    Invariant: ChargingStatus ∈ {UNBOTHERED, BOTHERED}.

    UNBOTHERED — sessionen afsluttedes uden fejl (AFSLUTTET).
    BOTHERED   — en fejl opstod under sessionen (FEJLET).

    Starter som None og sættes kun ved AFSLUTTET eller FEJLET.

    Event Storming events: 'CHARGING_STOPPED' → UNBOTHERED,
                           'UNEXPECTED_STOPPAGE' → BOTHERED.
    """
    UNBOTHERED = "UNBOTHERED"
    BOTHERED   = "BOTHERED"


# ---------------------------------------------------------------------------
# Identifikations-Value Objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UserID:
    """
    Identificerer den EV-bruger der initierer sessionen.
    Uforanderlig reference — aldrig et mutable objekt.

    Event Storming command: 'Opret Session'.
    """
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("UserID må ikke være tom")

    def __str__(self) -> str:
        return self.value


# ---------------------------------------------------------------------------
# Tids-Value Objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StartTime:
    """
    Tidspunkt for opladningsstart — sættes når sessionen skifter til AKTIV.

    Event Storming event: 'SESSION_STARTED'.
    """
    value: datetime

    def __str__(self) -> str:
        return self.value.isoformat()


@dataclass(frozen=True)
class EndTime:
    """
    Tidspunkt for opladningsafslutning — sættes når sessionen skifter til AFSLUTTET.

    Event Storming event: 'CHARGING_STOPPED'.
    """
    value: datetime

    def __str__(self) -> str:
        return self.value.isoformat()


@dataclass(frozen=True)
class EventTime:
    """
    Tidsstempel for et logget Event på sessionen.
    Bruges af Event-entiteten.

    Event Storming: audit trail for alle tilstandsovergange.
    """
    value: datetime

    def __str__(self) -> str:
        return self.value.isoformat()


# ---------------------------------------------------------------------------
# Energi og pris Value Objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EnergyDelivered:
    """
    Leveret energi i kWh ved sessionens afslutning.
    Invariant: EnergyDelivered ≥ 0 — aldrig negativ.

    Event Storming event: 'CHARGING_STOPPED' — sættes ét enkelt sted.
    """
    value: float

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError(
                f"EnergyDelivered kan ikke være negativ, fik: {self.value}"
            )

    def __str__(self) -> str:
        return f"{self.value} kWh"


@dataclass(frozen=True)
class AppliedSpotPrice:
    """
    Låst spotpris i DKK/kWh.
    Invariant: Sættes præcist én gang ved SESSION_AUTHORIZED og
               må ALDRIG overskrives bagefter — hverken i applikationslaget
               eller infrastrukturlaget.

    Event Storming event: 'SESSION_AUTHORIZED'.
    """
    value: float  # DKK pr. kWh

    def __str__(self) -> str:
        return f"{self.value} DKK/kWh"


@dataclass(frozen=True)
class SessionCost:
    """
    Beregnet sessionspris i DKK.
    Formel: SessionCost = EnergyDelivered × AppliedSpotPrice.
    Invariant: Beregnes KUN ved CHARGING_STOPPED — aldrig tidligere.

    Event Storming event: 'CHARGING_STOPPED'.
    """
    value: float  # DKK

    def __str__(self) -> str:
        return f"{self.value:.2f} DKK"
