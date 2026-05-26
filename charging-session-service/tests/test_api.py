"""
API-tests — charging-session-service.

Tester REST API endpoints via Flask test client med in-memory repository.
Ingen databaseforbindelse påkrævet.
"""

import pytest
from unittest.mock import MagicMock

from app.application.session_application_service import SessionApplicationService
from app.domain.aggregates.charging_session import (
    ChargingSession,
    ChargingSessionID,
    SessionNotFound,
    SessionStatus,
)
from app.domain.value_objects.value_objects import (
    AppliedSpotPrice,
    ChargerType,
    UserID,
)
from app.main import create_app
from app.presentation.routes import create_blueprint


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _byg_session(
    session_id: str = "test-session-001",
    status: SessionStatus = SessionStatus.AFVENTER,
    price_area: str = "DK1",
) -> ChargingSession:
    """Hjælpefunktion der bygger en test-session."""
    return ChargingSession(
        session_id=ChargingSessionID(value=session_id),
        user_id=UserID(value="user-001"),
        charger_id="charger-001",
        charger_type=ChargerType.NORMAL_CHARGER,
        price_area=price_area,
        status=status,
        events=[],
    )


@pytest.fixture
def mock_service():
    return MagicMock(spec=SessionApplicationService)


@pytest.fixture
def client(mock_service):
    from flask import Flask
    app = Flask(__name__)
    bp = create_blueprint(mock_service)
    app.register_blueprint(bp)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, mock_service


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health_check(client):
    c, _ = client
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /sessions — Opret Session
# ---------------------------------------------------------------------------

class TestOpretSession:

    def test_opret_session_returnerer_201(self, client):
        c, svc = client
        svc.opret_session.return_value = _byg_session()

        resp = c.post("/sessions", json={
            "user_id":      "user-001",
            "charger_id":   "charger-001",
            "charger_type": "Normal Charger",
            "price_area":   "DK1",
        })

        assert resp.status_code == 201
        data = resp.get_json()
        assert data["session_id"] == "test-session-001"
        assert data["status"] == "AFVENTER"

    def test_opret_session_manglende_felt_returnerer_400(self, client):
        c, _ = client
        resp = c.post("/sessions", json={
            "user_id": "user-001",
            "charger_id": "charger-001",
            # mangler charger_type og price_area
        })
        assert resp.status_code == 400
        assert "fejl" in resp.get_json()

    def test_opret_session_ugyldig_charger_type_returnerer_400(self, client):
        c, svc = client
        svc.opret_session.side_effect = ValueError("'Super Charger' is not a valid ChargerType")

        resp = c.post("/sessions", json={
            "user_id":      "user-001",
            "charger_id":   "charger-001",
            "charger_type": "Super Charger",
            "price_area":   "DK1",
        })
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /sessions/<id>/autoriser
# ---------------------------------------------------------------------------

class TestAutorisering:

    def test_autorisering_returnerer_200(self, client):
        c, svc = client
        session = _byg_session(status=SessionStatus.AUTORISERET)
        session.applied_spot_price = AppliedSpotPrice(value=1.25)
        svc.autoriser_session.return_value = session

        resp = c.post("/sessions/test-session-001/autoriser")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "AUTORISERET"
        assert data["applied_spot_price"] == 1.25

    def test_autorisering_af_ukendt_session_returnerer_404(self, client):
        c, svc = client
        svc.autoriser_session.side_effect = SessionNotFound("ukendt-id")
        resp = c.post("/sessions/ukendt-id/autoriser")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /sessions/<id>/start
# ---------------------------------------------------------------------------

class TestStartOpladning:

    def test_start_returnerer_200(self, client):
        c, svc = client
        session = _byg_session(status=SessionStatus.AKTIV)
        session.applied_spot_price = AppliedSpotPrice(value=1.25)
        svc.start_opladning.return_value = session

        resp = c.post("/sessions/test-session-001/start")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "AKTIV"

    def test_start_af_ukendt_session_returnerer_404(self, client):
        c, svc = client
        svc.start_opladning.side_effect = SessionNotFound("x")
        resp = c.post("/sessions/x/start")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /sessions/<id>/stop
# ---------------------------------------------------------------------------

class TestStopOpladning:

    def test_stop_returnerer_200_med_session_cost(self, client):
        c, svc = client
        from app.domain.value_objects.value_objects import EnergyDelivered, SessionCost
        session = _byg_session(status=SessionStatus.AFSLUTTET)
        session.applied_spot_price = AppliedSpotPrice(value=2.00)
        session.energy_delivered = EnergyDelivered(value=10.0)
        session.session_cost = SessionCost(value=20.0)
        svc.stop_opladning.return_value = session

        resp = c.post("/sessions/test-session-001/stop", json={"energy_delivered_kwh": 10.0})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "AFSLUTTET"
        assert data["session_cost"] == 20.0

    def test_stop_uden_energy_returnerer_400(self, client):
        c, _ = client
        resp = c.post("/sessions/test-session-001/stop", json={})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /sessions/<id>/fejl
# ---------------------------------------------------------------------------

class TestRegistrerFejl:

    def test_fejl_returnerer_200(self, client):
        c, svc = client
        session = _byg_session(status=SessionStatus.FEJLET)
        session.applied_spot_price = AppliedSpotPrice(value=1.25)
        svc.registrer_fejl.return_value = session

        resp = c.post("/sessions/test-session-001/fejl")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "FEJLET"


# ---------------------------------------------------------------------------
# GET /sessions + GET /sessions/<id>
# ---------------------------------------------------------------------------

class TestHentSessions:

    def test_hent_alle_sessions(self, client):
        c, svc = client
        svc.hent_alle_sessions.return_value = [_byg_session(), _byg_session("session-2")]
        resp = c.get("/sessions")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 2

    def test_hent_enkelt_session(self, client):
        c, svc = client
        svc.hent_session.return_value = _byg_session()
        resp = c.get("/sessions/test-session-001")
        assert resp.status_code == 200
        assert resp.get_json()["session_id"] == "test-session-001"

    def test_hent_ukendt_session_returnerer_404(self, client):
        c, svc = client
        svc.hent_session.side_effect = SessionNotFound("x")
        resp = c.get("/sessions/x")
        assert resp.status_code == 404
