"""
Aggregat-rod: ChargingSession — Charging Session Bounded Context.

Al adgang til session-data og -adfærd sker UDELUKKENDE via ChargingSessionID.
Domæneregler håndhæves her — aldrig i applikations- eller infrastrukturlaget.

Event Storming kommandoer realiseret:
  - Opret Session        → opret_session()
  - Autoriser Session    → autoriser()
  - Start Opladning      → start_opladning()
  - Stop Opladning       → stop_opladning()
  - Registrer Fejl       → registrer_fejl()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from app.domain.value_objects.value_objects import (
    AppliedSpotPrice,
    ChargerType,
    EnergyDelivered,
    EndTime,
    EventTime,
    EventType,
    SessionCost,
    StartTime,
    UserID,
)


# ---------------------------------------------------------------------------
# Undtagelse
# ---------------------------------------------------------------------------

class SessionNotFound(Exception):
    """
    Hæves når session-data ikke kan lokaliseres via ChargingSessionID.

    Event Storming: svarende til 'Session ikke fundet' read model fejl.
    """
    def __init__(self, session_id: str) -> None:
        super().__init__(f"Session ikke fundet: {session_id}")
        self.session_id = session_id


# ---------------------------------------------------------------------------
# Tilstandsmaskine (intern til aggregatet)
# ---------------------------------------------------------------------------

class SessionStatus(Enum):
    """
    Gyldige tilstande i sessionens livscyklus.
    Tilstandsmaskine:
        AFVENTER → AUTORISERET → AKTIV → AFSLUTTET
                                 AKTIV → FEJLET

    Ingen andre overgange er tilladt — håndhæves i aggregatet.
    """
    AFVENTER = "AFVENTER"
    AUTORISERET = "AUTORISERET"
    AKTIV = "AKTIV"
    AFSLUTTET = "AFSLUTTET"
    FEJLET = "FEJLET"


# ---------------------------------------------------------------------------
# Event-entitet (logges på sessionen)
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """
    Entitet der repræsenterer et domæne-event logget under sessionens livscyklus.

    Felter (præcist som defineret i DDD-modellen):
        event_type — klassifikation (EventType value object)
        event_time — tidsstempel (EventTime value object)

    Database-nøgler (event_id, session_id) genereres udelukkende i
    infrastrukturlaget — de er ikke en del af domænet.

    Event Storming: audit trail for SESSION_AUTHORIZED, SESSION_STARTED,
                    CHARGING_STOPPED, UNEXPECTED_STOPPAGE.
    """
    event_type: EventType
    event_time: EventTime


# ---------------------------------------------------------------------------
# Aggregat-rod identifikator
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChargingSessionID:
    """
    Aggregat-rod-identifikator for ChargingSession.
    Al adgang til session-data sker via denne type.
    Placeret i aggregates-mappen — ikke i value_objects.

    Event Storming: reference i alle kommandoer og events.
    """
    value: str

    def __str__(self) -> str:
        return self.value

    @classmethod
    def ny(cls) -> "ChargingSessionID":
        """Genererer et nyt unikt ChargingSessionID."""
        return cls(value=str(uuid4()))


# ---------------------------------------------------------------------------
# Aggregat-rod: ChargingSession
# ---------------------------------------------------------------------------

@dataclass
class ChargingSession:
    """
    Aggregat-rod for Charging Session Bounded Context.
    Håndhæver alle domæneregler for sessionens livscyklus.

    Invarianter:
      1. AppliedSpotPrice låses præcist én gang ved SESSION_AUTHORIZED.
      2. SessionCost beregnes KUN ved CHARGING_STOPPED som
         EnergyDelivered × AppliedSpotPrice.
      3. EnergyDelivered er aldrig negativ (håndhæves af value object).
      4. Tilstandsovergange følger tilstandsmaskinen — ingen genveje.

    Event Storming kommandoer → metoder:
      Opret Session     → ChargingSession.opret_session(...)  [factory]
      Autoriser Session → .autoriser(applied_spot_price)
      Start Opladning   → .start_opladning()
      Stop Opladning    → .stop_opladning(energy_delivered)
      Registrer Fejl    → .registrer_fejl()
    """

    session_id: ChargingSessionID
    user_id: UserID
    charger_id: str
    charger_type: ChargerType
    price_area: str                # 'DK1' eller 'DK2' — gemt som streng, domænet kender ikke PriceArea-enum
    status: SessionStatus
    events: List[Event] = field(default_factory=list)

    # Sættes ved SESSION_AUTHORIZED
    applied_spot_price: Optional[AppliedSpotPrice] = None

    # Sættes ved SESSION_STARTED
    start_time: Optional[StartTime] = None

    # Sættes ved CHARGING_STOPPED
    end_time: Optional[EndTime] = None
    energy_delivered: Optional[EnergyDelivered] = None
    session_cost: Optional[SessionCost] = None

    # Domæne-events til dispatch (renses efter håndtering)
    _pending_events: List[object] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Factory-metode (Event Storming command: 'Opret Session')
    # ------------------------------------------------------------------

    @classmethod
    def opret_session(
        cls,
        user_id: UserID,
        charger_id: str,
        charger_type: ChargerType,
        price_area: str,
    ) -> "ChargingSession":
        """
        Factory-metode: opretter en ny session i AFVENTER-tilstand.
        price_area gemmes på sessionen så SpotPriceClient kan filtrere korrekt ved autorisering.

        Args:
            price_area: 'DK1' eller 'DK2'

        Event Storming command: 'Opret Session'.
        """
        session_id = ChargingSessionID.ny()
        return cls(
            session_id=session_id,
            user_id=user_id,
            charger_id=charger_id,
            charger_type=charger_type,
            price_area=price_area,
            status=SessionStatus.AFVENTER,
        )

    # ------------------------------------------------------------------
    # Tilstandsovergange
    # ------------------------------------------------------------------

    def autoriser(self, applied_spot_price: AppliedSpotPrice) -> None:
        """
        Overgår sessionen fra AFVENTER til AUTORISERET.
        Låser AppliedSpotPrice — må ALDRIG overskrives efter dette punkt.

        Invariant: Kan kun kaldes fra AFVENTER-tilstand.

        Event Storming command: 'Autoriser Session'.
        Event Storming event:   'SESSION_AUTHORIZED'.
        """
        if self.status != SessionStatus.AFVENTER:
            raise ValueError(
                f"Kan kun autorisere fra AFVENTER, nuværende tilstand: {self.status.value}"
            )
        self.applied_spot_price = applied_spot_price
        self.status = SessionStatus.AUTORISERET
        self._log_event(EventType.SESSION_AUTHORIZED)

    def start_opladning(self) -> None:
        """
        Overgår sessionen fra AUTORISERET til AKTIV.
        Sætter StartTime til nuværende tidspunkt.

        Invariant: Kan kun kaldes fra AUTORISERET-tilstand.

        Event Storming command: 'Start Opladning'.
        Event Storming event:   'SESSION_STARTED'.
        """
        if self.status != SessionStatus.AUTORISERET:
            raise ValueError(
                f"Kan kun starte opladning fra AUTORISERET, nuværende tilstand: {self.status.value}"
            )
        self.start_time = StartTime(value=datetime.now(timezone.utc))
        self.status = SessionStatus.AKTIV
        self._log_event(EventType.SESSION_STARTED)

    def stop_opladning(self, energy_delivered: EnergyDelivered) -> None:
        """
        Overgår sessionen fra AKTIV til AFSLUTTET.
        Beregner SessionCost = EnergyDelivered × AppliedSpotPrice.

        Invariant: Kan kun kaldes fra AKTIV-tilstand.
        Invariant: applied_spot_price SKAL være låst (er garanteret af autoriser).
        Invariant: EnergyDelivered ≥ 0 (håndhæves af value object).

        Event Storming command: 'Stop Opladning'.
        Event Storming event:   'CHARGING_STOPPED'.
        """
        if self.status != SessionStatus.AKTIV:
            raise ValueError(
                f"Kan kun stoppe opladning fra AKTIV, nuværende tilstand: {self.status.value}"
            )
        if self.applied_spot_price is None:
            raise ValueError("AppliedSpotPrice er ikke låst — autoriser session først")

        self.energy_delivered = energy_delivered
        self.end_time = EndTime(value=datetime.now(timezone.utc))
        self.session_cost = SessionCost(
            value=round(energy_delivered.value * self.applied_spot_price.value, 4)
        )
        self.status = SessionStatus.AFSLUTTET
        self._log_event(EventType.CHARGING_STOPPED)

    def registrer_fejl(self) -> None:
        """
        Overgår sessionen fra AKTIV til FEJLET.
        Kan kun forekomme under aktiv opladning.

        Invariant: Kan kun kaldes fra AKTIV-tilstand.

        Event Storming command: 'Registrer Fejl'.
        Event Storming event:   'UNEXPECTED_STOPPAGE'.
        """
        if self.status != SessionStatus.AKTIV:
            raise ValueError(
                f"Kan kun registrere fejl fra AKTIV, nuværende tilstand: {self.status.value}"
            )
        self.end_time = EndTime(value=datetime.now(timezone.utc))
        self.status = SessionStatus.FEJLET
        self._log_event(EventType.UNEXPECTED_STOPPAGE)

    # ------------------------------------------------------------------
    # Privat hjælpemetode
    # ------------------------------------------------------------------

    def _log_event(self, event_type: EventType) -> None:
        """Opretter og tilføjer et Event til sessionens audit trail."""
        event = Event(
            event_type=event_type,
            event_time=EventTime(value=datetime.now(timezone.utc)),
        )
        self.events.append(event)
