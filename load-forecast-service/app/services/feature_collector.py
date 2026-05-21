"""
Feature Collector — samler alle input-features til ML-forudsigelsen.

Features:
  - temperature          fra DMI (WeatherFeature)
  - wind_speed           fra DMI (WeatherFeature)
  - spot_price           gennemsnitlig day-ahead pris fra Energidataservice
  - hour_of_day          0-23
  - day_of_week          0=mandag … 6=søndag
  - historical_volume    antal afsluttede sessioner på same time+ugedag historisk
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import requests
from sqlalchemy import create_engine, text

if TYPE_CHECKING:
    from .dmi_client import WeatherFeature

logger = logging.getLogger(__name__)


@dataclass
class ForecastFeatures:
    """Samlede features klar til ML-modellen."""
    temperature:       float
    wind_speed:        float
    spot_price:        float
    hour_of_day:       int
    day_of_week:       int
    historical_volume: int


def collect_features(
    charger_id: str,
    session_db_uri: str,
    energidataservice_url: str,
    weather: "WeatherFeature",
) -> ForecastFeatures:
    """
    Samler alle features for det givne ladepunkt på nuværende tidspunkt.
    """
    now = datetime.utcnow()

    historical_volume = _get_historical_volume(charger_id, session_db_uri, now)
    spot_price        = _get_average_spot_price(energidataservice_url)

    features = ForecastFeatures(
        temperature=       weather.temperature if weather.temperature is not None else 10.0,
        wind_speed=        weather.wind_speed  if weather.wind_speed  is not None else 5.0,
        spot_price=        spot_price,
        hour_of_day=       now.hour,
        day_of_week=       now.weekday(),
        historical_volume= historical_volume,
    )
    logger.info("Features for %s: %s", charger_id, features)
    return features


def _get_historical_volume(charger_id: str, session_db_uri: str, now: datetime) -> int:
    """Tæller afsluttede sessioner for ladepunkt på same time + ugedag historisk."""
    if not session_db_uri:
        return 0
    try:
        engine = create_engine(session_db_uri)
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM charging_sessions
                    WHERE charger_id            = :charger_id
                      AND HOUR(session_start_time)      = :hour
                      AND DAYOFWEEK(session_start_time) = :dow
                      AND status = 'COMPLETED'
                    """
                ),
                {"charger_id": charger_id, "hour": now.hour, "dow": now.weekday() + 1},
            ).fetchone()
        return int(row[0]) if row else 0
    except Exception as exc:
        logger.error("Fejl ved historisk volumen for %s: %s", charger_id, exc)
        return 0


def _get_average_spot_price(url: str) -> float:
    """Henter dag-frem gennemsnitlig spotpris for DK1 (DKK/kWh)."""
    if not url:
        return 0.50
    try:
        params = {"filter": '{"PriceArea":["DK1"]}', "sort": "TimeDK asc", "limit": 24}
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        records = resp.json().get("records", [])
        if records:
            avg_mwh = sum(r.get("SpotPriceDKK", 0) for r in records) / len(records)
            return round(avg_mwh / 1000.0, 6)
    except Exception as exc:
        logger.error("Fejl ved hentning af spotpris forecast: %s", exc)
    return 0.50
