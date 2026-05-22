"""
HTTP-lag for ladesessioner.
Validerer input og delegerer til SessionApplicationService.
"""
import logging

import requests as http_requests
from flask import Blueprint, current_app, jsonify, request

from app.domain.aggregates.charging_session import SessionNotFound
from app.domain.value_objects import PriceArea
from app.infrastructure.external.spot_price_client import SpotPriceClient
from app.infrastructure.repositories.session_repository import SessionRepository
from app.application.session_service import SessionApplicationService

logger = logging.getLogger(__name__)
sessions_bp = Blueprint("sessions", __name__)


def _get_service() -> SessionApplicationService:
    spot_client: SpotPriceClient = current_app.extensions["spot_price_client"]
    return SessionApplicationService(SessionRepository(), spot_client)


# ──────────────────────────────────────────────
# POST /sessions/start
# ──────────────────────────────────────────────
@sessions_bp.route("/sessions/start", methods=["POST"])
def start_session():
    data = request.get_json() or {}

    required = ["charger_id", "connector_id", "contract_id", "price_area"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Manglende felter: {missing}"}), 400
    if data["price_area"] not in {a.value for a in PriceArea}:
        return jsonify({"error": "price_area skal være 'DK1' eller 'DK2'"}), 400

    session = _get_service().start_session(
        charger_id=data["charger_id"],
        connector_id=data["connector_id"],
        contract_id=data["contract_id"],
        price_area=data["price_area"],
    )
    return jsonify({"session_id": session.session_id, "status": session.status}), 201


# ──────────────────────────────────────────────
# POST /sessions/<id>/authorize
# ──────────────────────────────────────────────
@sessions_bp.route("/sessions/<session_id>/authorize", methods=["POST"])
def authorize_session(session_id):
    try:
        session = _get_service().authorize_session(session_id)
        return jsonify({"session_id": session_id, "status": session.status})
    except SessionNotFound:
        return jsonify({"error": "Session ikke fundet"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


# ──────────────────────────────────────────────
# PUT /sessions/<id>/meter
# ──────────────────────────────────────────────
@sessions_bp.route("/sessions/<session_id>/meter", methods=["PUT"])
def update_meter(session_id):
    data = request.get_json() or {}
    meter_value = data.get("meter_value")
    if meter_value is None:
        return jsonify({"error": "meter_value er påkrævet"}), 400

    try:
        session = _get_service().activate_session(session_id, float(meter_value))
        return jsonify({
            "session_id":  session_id,
            "status":      session.status,
            "meter_start": session.meter_start,
        })
    except SessionNotFound:
        return jsonify({"error": "Session ikke fundet"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


# ──────────────────────────────────────────────
# POST /sessions/<id>/stop
# ──────────────────────────────────────────────
@sessions_bp.route("/sessions/<session_id>/stop", methods=["POST"])
def stop_session(session_id):
    data = request.get_json() or {}
    meter_end = data.get("meter_end")
    if meter_end is None:
        return jsonify({"error": "meter_end er påkrævet"}), 400

    try:
        session = _get_service().stop_session(
            session_id=session_id,
            meter_end=float(meter_end),
            fault=bool(data.get("fault", False)),
            stop_reason=data.get("stop_reason", "Normal"),
        )
        _trigger_forecast(session.charger_id, session_id)
        return jsonify(session.to_dict()), 200
    except SessionNotFound:
        return jsonify({"error": "Session ikke fundet"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


def _trigger_forecast(charger_id: str, session_id: str) -> None:
    """Sender SessionCompleted event til Load Forecast Service (best-effort)."""
    url = f"{current_app.config.get('FORECAST_SERVICE_URL', '')}/forecast/trigger"
    try:
        resp = http_requests.post(
            url,
            json={"session_id": session_id, "charger_id": charger_id},
            timeout=5,
        )
        logger.info("Forecast trigger → HTTP %d for charger=%s", resp.status_code, charger_id)
    except http_requests.RequestException as exc:
        logger.warning("Forecast trigger fejlede (ikke kritisk): %s", exc)


# ──────────────────────────────────────────────
# GET /sessions/<id>
# ──────────────────────────────────────────────
@sessions_bp.route("/sessions/<session_id>", methods=["GET"])
def get_session(session_id):
    try:
        session = _get_service().get_session(session_id)
        return jsonify(session.to_dict())
    except SessionNotFound:
        return jsonify({"error": "Session ikke fundet"}), 404


# ──────────────────────────────────────────────
# GET /sessions
# ──────────────────────────────────────────────
@sessions_bp.route("/sessions", methods=["GET"])
def get_all_sessions():
    sessions = _get_service().list_sessions()
    return jsonify([s.to_dict() for s in sessions])
