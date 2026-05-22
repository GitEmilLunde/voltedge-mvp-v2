"""
SessionApplicationService: orkestrerer use cases for ladesessioner.

Koordinerer domæneaggregat, repository og ekstern spotprisklient.
Domænelogik ligger i ChargingSession — denne klasse håndterer kun flow.
"""
import logging
from datetime import datetime

from app.domain.aggregates.charging_session import ChargingSession
from app.domain.services.idle_fee_policy import IdleFeePolicy
from app.infrastructure.repositories.session_repository import SessionRepository
from app.infrastructure.external.spot_price_client import SpotPriceClient

logger = logging.getLogger(__name__)

_VALID_STOP_REASONS = frozenset({"Normal", "Timeout", "Fault", "Administrative"})


class SessionApplicationService:
    def __init__(self, repository: SessionRepository, spot_price_client: SpotPriceClient):
        self._repo = repository
        self._spot_client = spot_price_client
        self._idle_fee_policy = IdleFeePolicy()

    def start_session(
        self,
        charger_id: str,
        connector_id: str,
        contract_id: str,
        price_area: str,
    ) -> ChargingSession:
        now = datetime.utcnow()
        spot_price = self._spot_client.fetch(price_area, now)

        session = ChargingSession(
            charger_id=charger_id,
            connector_id=connector_id,
            contract_id=contract_id,
            price_area=price_area,
            status="PENDING",
            session_start_time=now,
            spot_price_dkk=spot_price.dkk_per_kwh,
        )
        self._repo.add(session)
        self._repo.save()
        logger.info("Session oprettet: %s, charger=%s", session.session_id, charger_id)
        return session

    def authorize_session(self, session_id: str) -> ChargingSession:
        session = self._repo.get_or_raise(session_id)
        session.authorize()
        self._repo.save()
        logger.info("Session autoriseret: %s", session_id)
        return session

    def activate_session(self, session_id: str, meter_start: float) -> ChargingSession:
        session = self._repo.get_or_raise(session_id)
        session.activate(meter_start)
        self._repo.save()
        logger.info("Session aktiveret: %s, meter_start=%.3f", session_id, meter_start)
        return session

    def stop_session(
        self,
        session_id: str,
        meter_end: float,
        fault: bool = False,
        stop_reason: str = "Normal",
    ) -> ChargingSession:
        session = self._repo.get_or_raise(session_id)
        stop_reason = stop_reason if stop_reason in _VALID_STOP_REASONS else "Normal"

        if fault:
            session.fault(stop_reason)
        else:
            cost = session.complete(meter_end, self._idle_fee_policy)
            session.stop_reason = stop_reason
            logger.info(
                "Session afsluttet: %s, energi=%.3f kWh, pris=%.4f DKK",
                session_id, session.energy_delivered, cost.total_dkk,
            )

        self._repo.save()
        return session

    def get_session(self, session_id: str) -> ChargingSession:
        return self._repo.get_or_raise(session_id)

    def list_sessions(self) -> list[ChargingSession]:
        return self._repo.list_all()
