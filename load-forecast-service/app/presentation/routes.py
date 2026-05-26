"""
REST API — Load Forecast Bounded Context.

Endpoints:
  POST  /forecast/træn          — Træn ML-model på historiske sessions
  POST  /forecast/forudsig      — Generer ForecastResult
  GET   /forecast               — Hent alle ForecastResults
  GET   /forecast/model         — Hent info om aktiv model
  GET   /health                 — Sundhedstjek
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from app.application.forecast_application_service import ForecastApplicationService
from app.domain.aggregates.forecast_model import ForecastResult


def create_blueprint(service: ForecastApplicationService) -> Blueprint:
    """Factory-funktion der opretter Flask Blueprint med injiceret service."""
    bp = Blueprint("forecast", __name__)

    # ------------------------------------------------------------------
    # Hjælpefunktion — serialisering
    # ------------------------------------------------------------------

    def result_til_dict(result: ForecastResult) -> dict:
        return {
            "forecast_id":      result.forecast_id,
            "model_id":         result.model_id,
            "hour_of_day":      result.time_feature.hour_of_day,
            "day_of_week":      result.time_feature.day_of_week,
            "spot_price":       result.price_features.spot_price,
            "session_count":    result.session_count.value,
            "predicted_count":  result.predicted_count,
            "forecast_timestamp": result.forecast_timestamp.isoformat(),
        }

    # ------------------------------------------------------------------
    # Sundhedstjek
    # ------------------------------------------------------------------

    @bp.get("/health")
    def health() -> Response:
        return jsonify({"status": "ok", "service": "load-forecast-service"})

    # ------------------------------------------------------------------
    # POST /forecast/træn — Træn model
    # ------------------------------------------------------------------

    @bp.post("/forecast/træn")
    def træn_model() -> Response:
        """
        Henter session-data fra charging-session-service og træner ForecastModel.

        Returns:
            200 OK med model-metadata
            500 ved træningsfejl
        """
        try:
            model = service.træn_model()
            return jsonify({
                "model_id":         model.model_id,
                "trained_at":       model.trained_at.isoformat(),
                "r2_score":         model.r2_score,
                "training_samples": model.training_samples,
            })
        except ValueError as exc:
            return jsonify({"fejl": str(exc)}), 500

    # ------------------------------------------------------------------
    # POST /forecast/forudsig — Generer prognose
    # ------------------------------------------------------------------

    @bp.post("/forecast/forudsig")
    def forudsig() -> Response:
        """
        Genererer en ForecastResult for de givne parametre.

        Body (JSON):
            hour_of_day: int 0–23 (påkrævet)
            day_of_week: int 1–7  (påkrævet)
            spot_price:  float    (påkrævet)

        Returns:
            201 Created med ForecastResult
            400 ved manglende/ugyldige felter
        """
        body = request.get_json(silent=True) or {}
        required = ["hour_of_day", "day_of_week", "spot_price"]
        missing = [f for f in required if f not in body]
        if missing:
            return jsonify({"fejl": f"Manglende felter: {', '.join(missing)}"}), 400

        try:
            result = service.generer_prognose(
                hour_of_day=int(body["hour_of_day"]),
                day_of_week=int(body["day_of_week"]),
                spot_price=float(body["spot_price"]),
            )
            return jsonify(result_til_dict(result)), 201
        except (ValueError, TypeError) as exc:
            return jsonify({"fejl": str(exc)}), 400

    # ------------------------------------------------------------------
    # GET /forecast — Hent alle prognoser
    # ------------------------------------------------------------------

    @bp.get("/forecast")
    def hent_prognoser() -> Response:
        """Returnerer alle gemte ForecastResults."""
        results = service.hent_prognoser()
        return jsonify([result_til_dict(r) for r in results])

    # ------------------------------------------------------------------
    # GET /forecast/model — Model-info
    # ------------------------------------------------------------------

    @bp.get("/forecast/model")
    def model_info() -> Response:
        """Returnerer metadata om den aktive ForecastModel."""
        info = service.hent_model_info()
        if info is None:
            return jsonify({"besked": "Ingen model trænet endnu"}), 404
        return jsonify(info)

    return bp
