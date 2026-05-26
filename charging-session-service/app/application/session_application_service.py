"""
Applikationsservice — Charging Session Bounded Context.

Orkestrerer use cases: henter aggregater, delegerer til domæneobjekter,
persisterer via repository. Ingen domæneregler håndhæves her.

Use cases realiseret:
  - opret_session       (Event Storming command: 'Opret Session')
  - autoriser_session   (Event Storming command: 'Autoriser Session')
  - start_opladning     (Event Storming command: 'Start Opladning')
  - stop_opladning      (Event Storming command: 'Stop Opladning')
  - registrer_fejl      (Event Storming command: 'Registrer Fejl')
  - hent_session        (Event Storming read model: 'Session detaljer')
  - hent_alle_sessions  (Event Storming read model: 'Alle sessions')
"""

from __future__ import annotations

import logging
from typing import List

from app.domain.aggregates.charging_session import (
    ChargingSession,
    ChargingSessionID,
    SessionNotFound,
)
from app.domain.value_objects.value_objects import (
    AppliedSpotPrice,
    ChargerType,
    EnergyDelivered,
    UserID,
)
from app.infrastructure.external.spot_price_client import PriceArea, SpotPriceClient
from app.infrastructure.repositories.session_repository import SessionRepository

logger = logging.getLogger(__name__)


class SessionApplicationService:
    """
    Applikationsservice der orkestrerer alle use cases for ChargingSession.

    Afhænger af:
        SessionRepository  — persistering
        SpotPriceClient    — spotpris-opslag ved autorisering
    """

    def __init__(
        self,
        repository: SessionRepository,
        spot_price_client: SpotPriceClient,
    ) -> None:
        self._repo = repository
        self._spot_price_client = spot_price_client

    # ------------------------------------------------------------------
    # Use cases (kommandoer)
    # ------------------------------------------------------------------

    def opret_session(
        self,
        user_id: str,
        charger_id: str,
        charger_type: str,
        price_area: str,
    ) -> ChargingSession:
        """
        Opretter en ny ChargingSession i AFVENTER-tilstand.
        price_area gemmes på sessionen og bruges ved autorisering.

        Args:
            user_id:      bruger-identifikator
            charger_id:   lader-identifikator
            charger_type: 'Normal Charger' eller 'Fast Charger'
            price_area:   'DK1' eller 'DK2'

        Returns:
            Den oprettede ChargingSession

        Event Storming command: 'Opret Session'.
        """
        session = ChargingSession.opret_session(
            user_id=UserID(value=user_id),
            charger_id=charger_id,
            charger_type=ChargerType(charger_type),
            price_area=price_area,
        )
        self._repo.gem(session)
        logger.info("Session oprettet: %s", session.session_id.value)
        return session

    def autoriser_session(self, session_id: str) -> ChargingSession:
        """
        Autoriserer sessionen og låser AppliedSpotPrice fra Energidataservice.
        Læser price_area fra sessionen og sender den til SpotPriceClient.

        Args:
            session_id: ChargingSessionID som streng

        Returns:
            Den opdaterede ChargingSession

        Raises:
            SessionNotFound: hvis sessionen ikke eksisterer

        Event Storming command: 'Autoriser Session'.
        AppliedSpotPrice låses her og må ALDRIG overskrives efterfølgende.
        """
        session = self._hent_eller_fejl(session_id)

        spot_record = self._spot_price_client.hent_aktuel_pris(
            PriceArea(session.price_area)
        )
        applied_price = AppliedSpotPrice(value=spot_record.to_applied_spot_price())

        session.autoriser(applied_price)
        self._repo.gem(session)
        logger.info(
            "Session autoriseret: %s, spotpris låst: %.4f DKK/kWh",
            session_id,
            applied_price.value,
        )
        return session

    def start_opladning(self, session_id: str) -> ChargingSession:
        """
        Starter opladningen — sessionen overgår til AKTIV.

        Raises:
            SessionNotFound: hvis sessionen ikke eksisterer

        Event Storming command: 'Start Opladning'.
        """
        session = self._hent_eller_fejl(session_id)
        session.start_opladning()
        self._repo.gem(session)
        logger.info("Opladning startet: %s", session_id)
        return session

    def stop_opladning(
        self,
        session_id: str,
        energy_delivered_kwh: float,
    ) -> ChargingSession:
        """
        Stopper opladningen og beregner SessionCost.

        Args:
            session_id:           ChargingSessionID som streng
            energy_delivered_kwh: Leveret energi i kWh (≥ 0)

        Raises:
            SessionNotFound: hvis sessionen ikke eksisterer

        Event Storming command: 'Stop Opladning'.
        SessionCost = EnergyDelivered × AppliedSpotPrice — beregnes i aggregatet.
        """
        session = self._hent_eller_fejl(session_id)
        session.stop_opladning(EnergyDelivered(value=energy_delivered_kwh))
        self._repo.gem(session)
        logger.info(
            "Opladning stoppet: %s, energi: %.2f kWh, pris: %.2f DKK",
            session_id,
            energy_delivered_kwh,
            session.session_cost.value if session.session_cost else 0,
        )
        return session

    def registrer_fejl(self, session_id: str) -> ChargingSession:
        """
        Registrerer en fejl på den aktive session (AKTIV → FEJLET).

        Raises:
            SessionNotFound: hvis sessionen ikke eksisterer

        Event Storming command: 'Registrer Fejl'.
        """
        session = self._hent_eller_fejl(session_id)
        session.registrer_fejl()
        self._repo.gem(session)
        logger.warning("Fejl registreret på session: %s", session_id)
        return session

    # ------------------------------------------------------------------
    # Use cases (forespørgsler / read models)
    # ------------------------------------------------------------------

    def hent_session(self, session_id: str) -> ChargingSession:
        """
        Henter en enkelt session via ChargingSessionID.

        Raises:
            SessionNotFound: hvis sessionen ikke eksisterer
        """
        return self._hent_eller_fejl(session_id)

    def hent_alle_sessions(self) -> List[ChargingSession]:
        """Returnerer alle kendte ChargingSessions."""
        return self._repo.hent_alle()

    # ------------------------------------------------------------------
    # Privat hjælpemetode
    # ------------------------------------------------------------------

    def _hent_eller_fejl(self, session_id: str) -> ChargingSession:
        """Henter session eller hæver SessionNotFound."""
        session = self._repo.hent(ChargingSessionID(value=session_id))
        if session is None:
            raise SessionNotFound(session_id)
        return session
