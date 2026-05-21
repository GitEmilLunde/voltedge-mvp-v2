import logging
from flask import Blueprint, current_app, jsonify, request

from . import db
from .models import ForecastResult
from .services.dmi_client import get_weather_features
from .services.feature_collector import collect_features
from .services.forecast_engine import predict_load_index

logger = logging.getLogger(__name__)
forecast_bp = Blueprint("forecast", __name__)


# ──────────────────────────────────────────────
# POST /forecast/trigger
# ──────────────────────────────────────────────
@forecast_bp.route("/forecast/trigger", methods=["POST"])
def trigger_forecast():
    """
    Modtager SessionCompleted event fra Charging Session Service.
    Indsamler features, kører ML-model og gemmer ForecastResult.
    """
    data = request.get_json() or {}
    charger_id = data.get("charger_id")
    session_id = data.get("session_id", "unknown")

    if not charger_id:
        return jsonify({"error": "charger_id er påkrævet"}), 400

    logger.info("Forecast trigger: session=%s charger=%s", session_id, charger_id)

    # Hent vejrdata fra DMI
    weather = get_weather_features(current_app.config.get("DMI_API_URL", ""))

    # Saml alle features
    features = collect_features(
        charger_id=charger_id,
        session_db_uri=current_app.config.get("SESSION_DB_URI", ""),
        energidataservice_url=current_app.config.get("ENERGIDATASERVICE_URL", ""),
        weather=weather,
    )

    # Kør ML-model
    load_index = predict_load_index(features)

    # Gem resultat
    result = ForecastResult(
        charger_id=               charger_id,
        load_index=               load_index,
        temperature=              features.temperature,
        wind_speed=               features.wind_speed,
        spot_price_forecast=      features.spot_price,
        historical_session_volume=features.historical_volume,
    )
    db.session.add(result)
    db.session.commit()

    logger.info("Forecast gemt: %s LoadIndex=%.4f", result.forecast_id, load_index)
    return jsonify({"forecast_id": result.forecast_id, "status": "created"}), 201


# ──────────────────────────────────────────────
# GET /forecast/<charger_id>
# ──────────────────────────────────────────────
@forecast_bp.route("/forecast/<charger_id>", methods=["GET"])
def get_forecast(charger_id):
    """Returnerer seneste forecast for det angivne ladepunkt."""
    result = (
        ForecastResult.query
        .filter_by(charger_id=charger_id)
        .order_by(ForecastResult.generated_at.desc())
        .first()
    )
    if not result:
        return jsonify({"error": f"Ingen forecast fundet for charger '{charger_id}'"}), 404
    return jsonify(result.to_dict())
