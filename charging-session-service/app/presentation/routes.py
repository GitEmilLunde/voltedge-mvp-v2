"""
REST API — Charging Session Bounded Context.

Præsentationslaget oversætter HTTP-requests til applikationsservice-kald
og serialiserer domæne-objekter til JSON.

Ingen domæneregler eller forretningslogik håndhæves her.

Endpoints:
  POST   /sessions                        — Opret Session
  POST   /sessions/<id>/autoriser         — Autoriser Session
  POST   /sessions/<id>/start             — Start Opladning
  POST   /sessions/<id>/stop              — Stop Opladning
  POST   /sessions/<id>/fejl              — Registrer Fejl
  GET    /sessions/<id>                   — Hent Session
  GET    /sessions                        — Hent alle Sessions
  GET    /health                          — Sundhedstjek
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from app.application.session_application_service import SessionApplicationService
from app.domain.aggregates.charging_session import ChargingSession, SessionNotFound


def create_blueprint(service: SessionApplicationService) -> Blueprint:
    """Factory-funktion der opretter Flask Blueprint med injiceret service."""
    bp = Blueprint("sessions", __name__)

    # ------------------------------------------------------------------
    # Hjælpefunktion — serialisering
    # ------------------------------------------------------------------

    def session_til_dict(session: ChargingSession) -> dict:
        """Konverterer et ChargingSession-aggregat til et JSON-serialiserbart dict."""
        return {
            "session_id":         session.session_id.value,
            "user_id":            session.user_id.value,
            "charger_id":         session.charger_id,
            "charger_type":       session.charger_type.value,
            "price_area":         session.price_area,
            "status":             session.status.value,
            "applied_spot_price": session.applied_spot_price.value
                                  if session.applied_spot_price else None,
            "start_time":         session.start_time.value.isoformat()
                                  if session.start_time else None,
            "end_time":           session.end_time.value.isoformat()
                                  if session.end_time else None,
            "energy_delivered":   session.energy_delivered.value
                                  if session.energy_delivered else None,
            "session_cost":       session.session_cost.value
                                  if session.session_cost else None,
            "charging_status":    session.charging_status.value
                                  if session.charging_status else None,
            "events": [
                {
                    "error_type": evt.error_type.value if evt.error_type else None,
                    "event_time": evt.event_time.value.isoformat(),
                }
                for evt in session.events
            ],
        }

    # ------------------------------------------------------------------
    # Sundhedstjek
    # ------------------------------------------------------------------

    @bp.get("/health")
    def health() -> Response:
        """Returnerer 200 OK når servicen kører."""
        return jsonify({"status": "ok", "service": "charging-session-service"})

    # ------------------------------------------------------------------
    # POST /sessions — Opret Session
    # ------------------------------------------------------------------

    @bp.post("/sessions")
    def opret_session() -> Response:
        """
        Opretter en ny ChargingSession i AFVENTER-tilstand.

        Body (JSON):
            user_id:      string (påkrævet)
            charger_id:   string (påkrævet)
            charger_type: 'Normal Charger' eller 'Fast Charger' (påkrævet)
            price_area:   'DK1' eller 'DK2' (påkrævet)

        Returns:
            201 Created med session-data
            400 Bad Request ved manglende/ugyldige felter
        """
        body = request.get_json(silent=True) or {}
        required = ["user_id", "charger_id", "charger_type", "price_area"]
        missing = [f for f in required if not body.get(f)]
        if missing:
            return jsonify({"fejl": f"Manglende felter: {', '.join(missing)}"}), 400

        try:
            session = service.opret_session(
                user_id=body["user_id"],
                charger_id=body["charger_id"],
                charger_type=body["charger_type"],
                price_area=body["price_area"],
            )
            return jsonify(session_til_dict(session)), 201
        except (ValueError, KeyError) as exc:
            return jsonify({"fejl": str(exc)}), 400

    # ------------------------------------------------------------------
    # POST /sessions/<id>/autoriser — Autoriser Session
    # ------------------------------------------------------------------

    @bp.post("/sessions/<session_id>/autoriser")
    def autoriser_session(session_id: str) -> Response:
        """
        Autoriserer sessionen og låser AppliedSpotPrice fra Energidataservice.

        Returns:
            200 OK med opdateret session
            404 Not Found hvis session ikke eksisterer
            400 Bad Request ved ugyldig tilstandsovergang
        """
        try:
            session = service.autoriser_session(session_id)
            return jsonify(session_til_dict(session))
        except SessionNotFound as exc:
            return jsonify({"fejl": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"fejl": str(exc)}), 400

    # ------------------------------------------------------------------
    # POST /sessions/<id>/start — Start Opladning
    # ------------------------------------------------------------------

    @bp.post("/sessions/<session_id>/start")
    def start_opladning(session_id: str) -> Response:
        """
        Starter opladningen — session overgår til AKTIV.

        Returns:
            200 OK med opdateret session
            404 Not Found
            400 Bad Request
        """
        try:
            session = service.start_opladning(session_id)
            return jsonify(session_til_dict(session))
        except SessionNotFound as exc:
            return jsonify({"fejl": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"fejl": str(exc)}), 400

    # ------------------------------------------------------------------
    # POST /sessions/<id>/stop — Stop Opladning
    # ------------------------------------------------------------------

    @bp.post("/sessions/<session_id>/stop")
    def stop_opladning(session_id: str) -> Response:
        """
        Stopper opladningen og beregner SessionCost.

        Body (JSON):
            energy_delivered_kwh: float ≥ 0 (påkrævet)

        Returns:
            200 OK med session inkl. session_cost
            404 Not Found
            400 Bad Request
        """
        body = request.get_json(silent=True) or {}
        if "energy_delivered_kwh" not in body:
            return jsonify({"fejl": "Manglende felt: energy_delivered_kwh"}), 400

        try:
            energy = float(body["energy_delivered_kwh"])
            session = service.stop_opladning(session_id, energy)
            return jsonify(session_til_dict(session))
        except SessionNotFound as exc:
            return jsonify({"fejl": str(exc)}), 404
        except (ValueError, TypeError) as exc:
            return jsonify({"fejl": str(exc)}), 400

    # ------------------------------------------------------------------
    # POST /sessions/<id>/fejl — Registrer Fejl
    # ------------------------------------------------------------------

    @bp.post("/sessions/<session_id>/fejl")
    def registrer_fejl(session_id: str) -> Response:
        """
        Registrerer en fejl på den aktive session (AKTIV → FEJLET).

        Returns:
            200 OK med opdateret session
            404 Not Found
            400 Bad Request
        """
        try:
            session = service.registrer_fejl(session_id)
            return jsonify(session_til_dict(session))
        except SessionNotFound as exc:
            return jsonify({"fejl": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"fejl": str(exc)}), 400

    # ------------------------------------------------------------------
    # GET /sessions/<id> — Hent Session
    # ------------------------------------------------------------------

    @bp.get("/sessions/<session_id>")
    def hent_session(session_id: str) -> Response:
        """
        Henter en enkelt ChargingSession via ChargingSessionID.

        Returns:
            200 OK med session-data
            404 Not Found
        """
        try:
            session = service.hent_session(session_id)
            return jsonify(session_til_dict(session))
        except SessionNotFound as exc:
            return jsonify({"fejl": str(exc)}), 404

    # ------------------------------------------------------------------
    # GET /sessions — Hent alle Sessions
    # ------------------------------------------------------------------

    @bp.get("/sessions")
    def hent_alle_sessions() -> Response:
        """
        Henter alle ChargingSessions.

        Returns:
            200 OK med liste af sessions
        """
        sessions = service.hent_alle_sessions()
        return jsonify([session_til_dict(s) for s in sessions])

    return bp
