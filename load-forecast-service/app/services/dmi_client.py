"""
DMI vejrdata klient — VoltEdge Load Forecast Service.

Henter temperatur og vindstyrke fra DMI Open Data API (metObs).
Returnerer WeatherFeature value object med fallback ved API-fejl.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class WeatherFeature:
    """Value object der repræsenterer vejrdata på et givent observationstidspunkt."""
    temperature: Optional[float]   # °C (temp_dry)
    wind_speed:  Optional[float]   # m/s (wind_speed)


def get_weather_features(base_url: str) -> WeatherFeature:
    """
    Henter seneste temperatur og vindstyrke fra DMI metObs API.
    Returnerer fallback-værdier (10°C / 5 m/s) hvis API er nede.
    """
    if not base_url:
        logger.warning("DMI_API_URL ikke konfigureret — bruger fallback vejrdata")
        return WeatherFeature(temperature=10.0, wind_speed=5.0)

    try:
        params = {
            "parameterId": "temp_dry,wind_speed",
            "limit": 10,
            "sortorder": "observed,DESC",
        }
        response = requests.get(base_url, params=params, timeout=5)
        response.raise_for_status()

        features = response.json().get("features", [])
        temperature: Optional[float] = None
        wind_speed:  Optional[float] = None

        for feat in features:
            props    = feat.get("properties", {})
            param_id = props.get("parameterId")
            value    = props.get("value")

            if param_id == "temp_dry" and temperature is None:
                temperature = float(value) if value is not None else None
            elif param_id == "wind_speed" and wind_speed is None:
                wind_speed = float(value) if value is not None else None

            if temperature is not None and wind_speed is not None:
                break

        logger.info("DMI vejrdata: temp=%.1f°C, vind=%.1f m/s", temperature or 0, wind_speed or 0)
        return WeatherFeature(temperature=temperature, wind_speed=wind_speed)

    except requests.RequestException as exc:
        logger.error("DMI API utilgængeligt: %s — bruger fallback", exc)
        return WeatherFeature(temperature=10.0, wind_speed=5.0)
