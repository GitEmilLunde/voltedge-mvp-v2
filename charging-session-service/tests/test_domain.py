"""
Domæne-tests — Charging Session Bounded Context.

Tester aggregat-regler, value object invarianter og tilstandsmaskinen
uden afhængighed til database eller HTTP.
"""

import pytest

from app.domain.aggregates.charging_session import (
    ChargingSession,
    ChargingSessionID,
    SessionNotFound,
    SessionStatus,
)
from app.domain.value_objects.value_objects import (
    AppliedSpotPrice,
    ChargerType,
    EnergyDelivered,
    EventType,
    SessionCost,
    UserID,
)


# ---------------------------------------------------------------------------
# Hjælpefunktion
# ---------------------------------------------------------------------------

def ny_session(price_area: str = "DK1") -> ChargingSession:
    """Opretter en test-session i AFVENTER-tilstand."""
    return ChargingSession.opret_session(
        user_id=UserID(value="user-001"),
        charger_id="charger-001",
        charger_type=ChargerType.NORMAL_CHARGER,
        price_area=price_area,
    )


# ---------------------------------------------------------------------------
# Tilstandsmaskine-tests
# ---------------------------------------------------------------------------

class TestTilstandsmaskine:

    def test_ny_session_er_i_afventer(self):
        session = ny_session()
        assert session.status == SessionStatus.AFVENTER

    def test_autoriser_ændrer_status_til_autoriseret(self):
        session = ny_session()
        session.autoriser(AppliedSpotPrice(value=1.25))
        assert session.status == SessionStatus.AUTORISERET

    def test_start_opladning_ændrer_status_til_aktiv(self):
        session = ny_session()
        session.autoriser(AppliedSpotPrice(value=1.25))
        session.start_opladning()
        assert session.status == SessionStatus.AKTIV

    def test_stop_opladning_ændrer_status_til_afsluttet(self):
        session = ny_session()
        session.autoriser(AppliedSpotPrice(value=1.25))
        session.start_opladning()
        session.stop_opladning(EnergyDelivered(value=20.0))
        assert session.status == SessionStatus.AFSLUTTET

    def test_registrer_fejl_ændrer_status_til_fejlet(self):
        session = ny_session()
        session.autoriser(AppliedSpotPrice(value=1.25))
        session.start_opladning()
        session.registrer_fejl()
        assert session.status == SessionStatus.FEJLET

    def test_kan_ikke_autorisere_fra_autoriseret(self):
        session = ny_session()
        session.autoriser(AppliedSpotPrice(value=1.25))
        with pytest.raises(ValueError, match="AFVENTER"):
            session.autoriser(AppliedSpotPrice(value=1.50))

    def test_kan_ikke_starte_fra_afventer(self):
        session = ny_session()
        with pytest.raises(ValueError, match="AUTORISERET"):
            session.start_opladning()

    def test_kan_ikke_stoppe_fra_autoriseret(self):
        session = ny_session()
        session.autoriser(AppliedSpotPrice(value=1.25))
        with pytest.raises(ValueError, match="AKTIV"):
            session.stop_opladning(EnergyDelivered(value=10.0))

    def test_kan_ikke_registrere_fejl_fra_afventer(self):
        session = ny_session()
        with pytest.raises(ValueError, match="AKTIV"):
            session.registrer_fejl()


# ---------------------------------------------------------------------------
# AppliedSpotPrice-tests (låsningsregel)
# ---------------------------------------------------------------------------

class TestAppliedSpotPrice:

    def test_applied_spot_price_er_none_ved_oprettelse(self):
        session = ny_session()
        assert session.applied_spot_price is None

    def test_applied_spot_price_låses_ved_autorisering(self):
        session = ny_session()
        pris = AppliedSpotPrice(value=1.42)
        session.autoriser(pris)
        assert session.applied_spot_price == pris

    def test_applied_spot_price_bevares_uændret_efter_stop(self):
        """AppliedSpotPrice må ALDRIG overskrives — testes eksplicit."""
        session = ny_session()
        original_pris = AppliedSpotPrice(value=1.42)
        session.autoriser(original_pris)
        session.start_opladning()
        session.stop_opladning(EnergyDelivered(value=15.0))
        assert session.applied_spot_price == original_pris

    def test_price_area_gemmes_på_session(self):
        session = ny_session(price_area="DK2")
        assert session.price_area == "DK2"


# ---------------------------------------------------------------------------
# SessionCost-beregning
# ---------------------------------------------------------------------------

class TestSessionCost:

    def test_session_cost_beregnes_korrekt(self):
        session = ny_session()
        session.autoriser(AppliedSpotPrice(value=2.00))
        session.start_opladning()
        session.stop_opladning(EnergyDelivered(value=10.0))
        # 10.0 kWh × 2.00 DKK/kWh = 20.00 DKK
        assert session.session_cost == SessionCost(value=20.0)

    def test_session_cost_er_none_ved_aktiv(self):
        session = ny_session()
        session.autoriser(AppliedSpotPrice(value=1.25))
        session.start_opladning()
        assert session.session_cost is None

    def test_session_cost_er_none_ved_fejl(self):
        session = ny_session()
        session.autoriser(AppliedSpotPrice(value=1.25))
        session.start_opladning()
        session.registrer_fejl()
        assert session.session_cost is None


# ---------------------------------------------------------------------------
# Value Object invarianter
# ---------------------------------------------------------------------------

class TestValueObjectInvarianter:

    def test_energy_delivered_kan_ikke_være_negativ(self):
        with pytest.raises(ValueError, match="negativ"):
            EnergyDelivered(value=-1.0)

    def test_energy_delivered_nul_er_tilladt(self):
        e = EnergyDelivered(value=0.0)
        assert e.value == 0.0

    def test_user_id_kan_ikke_være_tom(self):
        with pytest.raises(ValueError):
            UserID(value="")

    def test_charger_type_kun_gyldige_værdier(self):
        assert ChargerType("Normal Charger") == ChargerType.NORMAL_CHARGER
        assert ChargerType("Fast Charger") == ChargerType.FAST_CHARGER
        with pytest.raises(ValueError):
            ChargerType("Super Charger")

    def test_event_type_gyldige_værdier(self):
        assert EventType("SESSION_AUTHORIZED") == EventType.SESSION_AUTHORIZED
        assert EventType("CHARGING_STOPPED") == EventType.CHARGING_STOPPED


# ---------------------------------------------------------------------------
# ChargingSessionID
# ---------------------------------------------------------------------------

class TestChargingSessionID:

    def test_ny_genererer_unik_id(self):
        id1 = ChargingSessionID.ny()
        id2 = ChargingSessionID.ny()
        assert id1 != id2

    def test_session_id_er_frozen(self):
        sid = ChargingSessionID(value="abc-123")
        with pytest.raises((AttributeError, TypeError)):
            sid.value = "ændret"  # type: ignore


# ---------------------------------------------------------------------------
# Event-log
# ---------------------------------------------------------------------------

class TestEventLog:

    def test_ingen_events_ved_oprettelse(self):
        session = ny_session()
        assert session.events == []

    def test_session_authorized_event_logges_ved_autorisering(self):
        session = ny_session()
        session.autoriser(AppliedSpotPrice(value=1.0))
        assert any(e.event_type == EventType.SESSION_AUTHORIZED for e in session.events)

    def test_session_started_event_logges_ved_start(self):
        session = ny_session()
        session.autoriser(AppliedSpotPrice(value=1.0))
        session.start_opladning()
        assert any(e.event_type == EventType.SESSION_STARTED for e in session.events)

    def test_charging_stopped_event_logges_ved_stop(self):
        session = ny_session()
        session.autoriser(AppliedSpotPrice(value=1.0))
        session.start_opladning()
        session.stop_opladning(EnergyDelivered(value=5.0))
        assert any(e.event_type == EventType.CHARGING_STOPPED for e in session.events)

    def test_unexpected_stoppage_event_logges_ved_fejl(self):
        session = ny_session()
        session.autoriser(AppliedSpotPrice(value=1.0))
        session.start_opladning()
        session.registrer_fejl()
        assert any(e.event_type == EventType.UNEXPECTED_STOPPAGE for e in session.events)


# ---------------------------------------------------------------------------
# SessionNotFound
# ---------------------------------------------------------------------------

class TestSessionNotFound:

    def test_session_not_found_indeholder_session_id(self):
        exc = SessionNotFound("missing-id-123")
        assert "missing-id-123" in str(exc)
        assert exc.session_id == "missing-id-123"
