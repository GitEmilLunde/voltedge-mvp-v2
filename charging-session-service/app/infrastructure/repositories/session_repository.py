"""
SessionRepository — MySQL-persistering for Charging Session Bounded Context.

Ingen domæneregler håndhæves her.
Al mapping mellem database-rækker og domain-objekter sker i denne fil.

Metoder (præcist som defineret i modellen):
    gem        — INSERT eller UPDATE en session og dens events
    hent       — hent én session via ChargingSessionID
    hent_alle  — hent alle sessions
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.domain.aggregates.charging_session import (
    ChargingSession,
    ChargingSessionID,
    Event,
    SessionStatus,
)
from app.domain.value_objects.value_objects import (
    AppliedSpotPrice,
    ChargerType,
    ChargingStatus,
    EnergyDelivered,
    EndTime,
    ErrorType,
    EventTime,
    SessionCost,
    StartTime,
    UserID,
)

logger = logging.getLogger(__name__)


class SessionRepository:
    """
    Konkret repository for ChargingSession-aggregatet.
    Kommunikerer med charging_session_db via SQLAlchemy.

    Tabeller:
        charging_sessions — én række pr. ChargingSession-aggregat
        session_events    — én række pr. Event-entitet (ID genereres her)
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ------------------------------------------------------------------
    # Offentlige metoder
    # ------------------------------------------------------------------

    def gem(self, session: ChargingSession) -> None:
        """
        Persisterer en ChargingSession og alle dens events.
        Bruger ON DUPLICATE KEY UPDATE — idempotent ved gentagne kald.
        """
        with self._engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO charging_sessions
                        (session_id, user_id, charger_id, charger_type, price_area, status,
                         applied_spot_price, start_time, end_time,
                         energy_delivered, session_cost, charging_status)
                    VALUES
                        (:session_id, :user_id, :charger_id, :charger_type, :price_area, :status,
                         :applied_spot_price, :start_time, :end_time,
                         :energy_delivered, :session_cost, :charging_status)
                    ON DUPLICATE KEY UPDATE
                        status             = VALUES(status),
                        applied_spot_price = VALUES(applied_spot_price),
                        start_time         = VALUES(start_time),
                        end_time           = VALUES(end_time),
                        energy_delivered   = VALUES(energy_delivered),
                        session_cost       = VALUES(session_cost),
                        charging_status    = VALUES(charging_status)
                """),
                {
                    "session_id":         session.session_id.value,
                    "user_id":            session.user_id.value,
                    "charger_id":         session.charger_id,
                    "charger_type":       session.charger_type.value,
                    "price_area":         session.price_area,
                    "status":             session.status.value,
                    "applied_spot_price": session.applied_spot_price.value
                                          if session.applied_spot_price else None,
                    "start_time":         session.start_time.value
                                          if session.start_time else None,
                    "end_time":           session.end_time.value
                                          if session.end_time else None,
                    "energy_delivered":   session.energy_delivered.value
                                          if session.energy_delivered else None,
                    "session_cost":       session.session_cost.value
                                          if session.session_cost else None,
                    "charging_status":    session.charging_status.value
                                          if session.charging_status else None,
                },
            )

            # Events: generér database-ID her — ikke i domænet
            for evt in session.events:
                conn.execute(
                    text("""
                        INSERT IGNORE INTO session_events
                            (event_id, session_id, error_type, event_time)
                        VALUES
                            (:event_id, :session_id, :error_type, :event_time)
                    """),
                    {
                        "event_id":   str(uuid4()),
                        "session_id": session.session_id.value,
                        "error_type": evt.error_type.value if evt.error_type else None,
                        "event_time": evt.event_time.value,
                    },
                )

    def hent(self, session_id: ChargingSessionID) -> Optional[ChargingSession]:
        """
        Henter én ChargingSession og dens events via ChargingSessionID.
        Returnerer None hvis sessionen ikke eksisterer.
        """
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM charging_sessions WHERE session_id = :sid"),
                {"sid": session_id.value},
            ).mappings().first()

            if row is None:
                return None

            events = self._hent_events(conn, session_id.value)
            return self._map_til_aggregat(dict(row), events)

    def hent_alle(self) -> List[ChargingSession]:
        """Henter alle ChargingSessions sorteret efter oprettelsestidspunkt."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM charging_sessions ORDER BY created_at DESC")
            ).mappings().all()

            result = []
            for row in rows:
                events = self._hent_events(conn, row["session_id"])
                result.append(self._map_til_aggregat(dict(row), events))
            return result

    # ------------------------------------------------------------------
    # Private hjælpemetoder
    # ------------------------------------------------------------------

    def _hent_events(self, conn, session_id: str) -> List[Event]:
        """Henter alle events for en given session."""
        rows = conn.execute(
            text(
                "SELECT error_type, event_time FROM session_events "
                "WHERE session_id = :sid ORDER BY event_time"
            ),
            {"sid": session_id},
        ).mappings().all()

        return [
            Event(
                event_time=EventTime(value=self._parse_dt(row["event_time"])),
                error_type=ErrorType(row["error_type"]) if row["error_type"] else None,
            )
            for row in rows
        ]

    @staticmethod
    def _map_til_aggregat(row: dict, events: List[Event]) -> ChargingSession:
        """Mapper en database-række til et ChargingSession-aggregat."""
        return ChargingSession(
            session_id=ChargingSessionID(value=row["session_id"]),
            user_id=UserID(value=row["user_id"]),
            charger_id=row["charger_id"],
            charger_type=ChargerType(row["charger_type"]),
            price_area=row["price_area"],
            status=SessionStatus(row["status"]),
            events=events,
            applied_spot_price=AppliedSpotPrice(value=float(row["applied_spot_price"]))
                               if row.get("applied_spot_price") is not None else None,
            start_time=StartTime(
                value=SessionRepository._parse_dt(row["start_time"])
            ) if row.get("start_time") else None,
            end_time=EndTime(
                value=SessionRepository._parse_dt(row["end_time"])
            ) if row.get("end_time") else None,
            energy_delivered=EnergyDelivered(value=float(row["energy_delivered"]))
                             if row.get("energy_delivered") is not None else None,
            session_cost=SessionCost(value=float(row["session_cost"]))
                         if row.get("session_cost") is not None else None,
            charging_status=ChargingStatus(row["charging_status"])
                            if row.get("charging_status") else None,
        )

    @staticmethod
    def _parse_dt(value) -> datetime:
        """Konverterer database-tidsstempel til datetime-objekt."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return datetime.utcnow()
