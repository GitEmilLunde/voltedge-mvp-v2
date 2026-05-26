"""
Domæne-events — Charging Session Bounded Context.

Disse dataklasser repræsenterer 'hvad der skete' og udgør
det faktuelle grundlag for eventuelle event handlers / projections.

Teknisk mekanisme: aggregatet samler events i _pending_events;
applikationslaget dispatcher dem efter persistering.

Event Storming: orange post-its → Python dataklasser.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SessionOprettet:
    """
    Hæves når en ny ChargingSession oprettes (AFVENTER-tilstand).

    Event Storming event: 'Session Oprettet'.
    """
    session_id: str
    user_id: str
    charger_id: str
    charger_type: str
    occurred_at: datetime


@dataclass(frozen=True)
class SessionAutoriseret:
    """
    Hæves når sessionen overgår til AUTORISERET.
    Indeholder den låste AppliedSpotPrice.

    Event Storming event: 'SESSION_AUTHORIZED'.
    """
    session_id: str
    applied_spot_price: float  # DKK/kWh — låst og uforanderlig
    occurred_at: datetime


@dataclass(frozen=True)
class OpladningStartet:
    """
    Hæves når sessionen overgår til AKTIV (opladning begynder).

    Event Storming event: 'SESSION_STARTED'.
    """
    session_id: str
    start_time: datetime
    occurred_at: datetime


@dataclass(frozen=True)
class OpladningStoppet:
    """
    Hæves når sessionen overgår til AFSLUTTET.
    Indeholder endelig energi og beregnet pris.

    Event Storming event: 'CHARGING_STOPPED'.
    """
    session_id: str
    energy_delivered: float   # kWh
    session_cost: float       # DKK
    occurred_at: datetime


@dataclass(frozen=True)
class FejlRegistreret:
    """
    Hæves når sessionen overgår til FEJLET fra AKTIV.

    Event Storming event: 'UNEXPECTED_STOPPAGE'.
    """
    session_id: str
    occurred_at: datetime
