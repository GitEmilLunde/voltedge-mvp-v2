import logging
from datetime import datetime

import requests
from flask import Blueprint, current_app, jsonify, request

from . import db
from .models import ChargingSession
from .services.cost_calculator import calculate_session_cost
from .services.idle_fee_service import calculate_idle_fee
from .services.session_lifecycle import transition
from .services.spot_price_service import get_spot_price

logger = logging.getLogger(__name__)
sessions_bp = Blueprint("sessions", __name__)

_VALID_STOP_REASONS = ("Normal", "Timeout", "Fault", "Administrative")


# ──────────────────────────────────────────────
# POST /sessions/start
# ──────────────────────────────────────────────
@sessions_bp.route("/sessions/start", methods=["POST"])
def start_session():
    """Opretter ny session med status PENDING og henter aktuel spotpris."""
    data = request.get_json() or {}

    required = ["charger_id", "connector_id", "contract_id", "charger_type", "price_area"]
    missing = [f for f in required if f not in data]
    if missing:
        logger.warning("Session start afvist — manglende felter: %s", missing)
        return jsonify({"error": f"Manglende felter: {missing}"}), 400

    if data["charger_type"] not in ("fast", "normal"):
        return jsonify({"error": "charger_type skal være 'fast' eller 'normal'"}), 400
    if data["price_area"] not in ("DK1", "DK2"):
        return jsonify({"error": "price_area skal være 'DK1' eller 'DK2'"}), 400

    now = datetime.utcnow()
    spot_price = get_spot_price(
        data["price_area"], now,
        current_app.config.get("ENERGIDATASERVICE_URL", "")
    )

    session = ChargingSession(
        charger_id=data["charger_id"],
        connector_id=data["connector_id"],
        contract_id=data["contract_id"],
        charger_type=data["charger_type"],
        price_area=data["price_area"],
        status="PENDING",
        session_start_time=now,
        spot_price_dkk=spot_price,
    )
    db.session.add(session)
    db.session.commit()

    logger.info("Session oprettet: %s, charger=%s", session.session_id, data["charger_id"])
    return jsonify({"session_id": session.session_id, "status": session.status}), 201


# ──────────────────────────────────────────────
# POST /sessions/<id>/authorize
# ──────────────────────────────────────────────
@sessions_bp.route("/sessions/<session_id>/authorize", methods=["POST"])
def authorize_session(session_id):
    """Sætter session fra PENDING → AUTHORIZED."""
    session = db.session.get(ChargingSession, session_id)
    if not session:
        return jsonify({"error": "Session ikke fundet"}), 404

    try:
        session.status = transition(session.status, "AUTHORIZED")
        db.session.commit()
        logger.info("Session autoriseret: %s", session_id)
        return jsonify({"session_id": session_id, "status": session.status})
    except ValueError as exc:
        logger.warning("Ulovlig overgang for %s: %s", session_id, exc)
        return jsonify({"error": str(exc)}), 400


# ──────────────────────────────────────────────
# PUT /sessions/<id>/meter
# ──────────────────────────────────────────────
@sessions_bp.route("/sessions/<session_id>/meter", methods=["PUT"])
def update_meter(session_id):
    """Opdaterer meter_start og sætter session fra AUTHORIZED → ACTIVE."""
    session = db.session.get(ChargingSession, session_id)
    if not session:
        return jsonify({"error": "Session ikke fundet"}), 404

    data = request.get_json() or {}
    meter_value = data.get("meter_value")
    if meter_value is None:
        return jsonify({"error": "meter_value er påkrævet"}), 400

    try:
        session.status = transition(session.status, "ACTIVE")
        session.meter_start = float(meter_value)
        db.session.commit()
        logger.info("Måler sat: %s, meter_start=%.3f", session_id, session.meter_start)
        return jsonify({
            "session_id":  session_id,
            "status":      session.status,
            "meter_start": session.meter_start,
        })
    except ValueError as exc:
        logger.warning("Ulovlig overgang for %s: %s", session_id, exc)
        return jsonify({"error": str(exc)}), 400


# ──────────────────────────────────────────────
# POST /sessions/<id>/stop
# ──────────────────────────────────────────────
@sessions_bp.route("/sessions/<session_id>/stop", methods=["POST"])
def stop_session(session_id):
    """Afslutter session, beregner pris og trigge forecast."""
    session = db.session.get(ChargingSession, session_id)
    if not session:
        return jsonify({"error": "Session ikke fundet"}), 404

    data = request.get_json() or {}
    meter_end = data.get("meter_end")
    if meter_end is None:
        return jsonify({"error": "meter_end er påkrævet"}), 400

    fault = bool(data.get("fault", False))
    new_status = "FAULTED" if fault else "COMPLETED"
    stop_reason = data.get("stop_reason", "Normal")
    if stop_reason not in _VALID_STOP_REASONS:
        stop_reason = "Normal"

    try:
        session.status = transition(session.status, new_status)
    except ValueError as exc:
        logger.warning("Ulovlig overgang for %s: %s", session_id, exc)
        return jsonify({"error": str(exc)}), 400

    session.session_end_time = datetime.utcnow()
    session.meter_end = float(meter_end)
    session.energy_delivered = max(0.0, (session.meter_end or 0) - (session.meter_start or 0))
    session.idle_fee = calculate_idle_fee(session.session_start_time, session.session_end_time)
    session.session_cost = calculate_session_cost(
        session.energy_delivered, session.spot_price_dkk, session.idle_fee
    )
    session.stop_reason = stop_reason
    db.session.commit()

    logger.info(
        "Session afsluttet: %s status=%s energi=%.3f kWh pris=%.4f DKK",
        session_id, session.status, session.energy_delivered, session.session_cost
    )

    # Asynkron notifikation til Load Forecast Service (ikke-kritisk)
    _trigger_forecast(session.charger_id, session_id)

    return jsonify(session.to_dict()), 200


def _trigger_forecast(charger_id: str, session_id: str) -> None:
    """Sender SessionCompleted event til Load Forecast Service (best-effort)."""
    url = f"{current_app.config.get('FORECAST_SERVICE_URL', '')}/forecast/trigger"
    try:
        resp = requests.post(
            url,
            json={"session_id": session_id, "charger_id": charger_id},
            timeout=5,
        )
        logger.info("Forecast trigger → HTTP %d for charger=%s", resp.status_code, charger_id)
    except requests.RequestException as exc:
        logger.warning("Forecast trigger fejlede (ikke kritisk): %s", exc)


# ──────────────────────────────────────────────
# GET /sessions/<id>
# ──────────────────────────────────────────────
@sessions_bp.route("/sessions/<session_id>", methods=["GET"])
def get_session(session_id):
    session = db.session.get(ChargingSession, session_id)
    if not session:
        return jsonify({"error": "Session ikke fundet"}), 404
    return jsonify(session.to_dict())


# ──────────────────────────────────────────────
# GET /sessions
# ──────────────────────────────────────────────
@sessions_bp.route("/sessions", methods=["GET"])
def get_all_sessions():
    sessions = ChargingSession.query.order_by(ChargingSession.created_at.desc()).all()
    return jsonify([s.to_dict() for s in sessions])
