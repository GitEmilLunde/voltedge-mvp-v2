"""
ML-forudsigelsesmotor — Load Forecast Service.

Indlæser scikit-learn model (model.pkl) ved service-start og
returnerer LoadIndex (estimeret session-volumen per time) som float.

Ved manglende model.pkl bruges en regelbaseret heuristik som fallback
så servicen altid kan levere et svar.
"""
import logging
import os
import pickle
from typing import Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .feature_collector import ForecastFeatures

logger = logging.getLogger(__name__)

_model = None
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "../../ml/model.pkl")


def load_model() -> None:
    """Indlæser model.pkl fra disk. Kaldes én gang ved service-start."""
    global _model
    path = os.path.abspath(_MODEL_PATH)
    if os.path.exists(path):
        try:
            with open(path, "rb") as fh:
                _model = pickle.load(fh)
            logger.info("ML-model indlæst fra %s", path)
        except Exception as exc:
            logger.error("Fejl ved indlæsning af model.pkl: %s", exc)
    else:
        logger.warning("model.pkl ikke fundet på %s — bruger heuristisk fallback", path)


def predict_load_index(features: "ForecastFeatures") -> float:
    """
    Forudsiger LoadIndex for de næste 24 timer baseret på indsamlede features.

    Feature-rækkefølge matcher notebooken:
      [temperature, wind_speed, spot_price, hour_of_day, day_of_week, historical_volume]
    """
    feature_vector = np.array([[
        features.temperature,
        features.wind_speed,
        features.spot_price,
        features.hour_of_day,
        features.day_of_week,
        features.historical_volume,
    ]])

    if _model is not None:
        try:
            prediction = float(_model.predict(feature_vector)[0])
            load_index = max(0.0, round(prediction, 4))
            logger.info("LoadIndex (model): %.4f", load_index)
            return load_index
        except Exception as exc:
            logger.error("ML-forudsigelse fejlede: %s — bruger heuristik", exc)

    # Heuristisk fallback baseret på tidspunkt på dagen
    hour = features.hour_of_day
    if 7 <= hour <= 9 or 16 <= hour <= 19:       # morgen/eftermiddags-spidstid
        base = 0.80
    elif 10 <= hour <= 15:                         # dagtimer
        base = 0.50
    else:                                           # nat/tidlig morgen
        base = 0.20

    load_index = round(base + features.historical_volume * 0.05, 4)
    logger.info("LoadIndex (heuristik): %.4f", load_index)
    return load_index
