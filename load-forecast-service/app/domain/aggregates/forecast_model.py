"""
Aggregat-rod: ForecastModel — Load Forecast Bounded Context.

ForecastModel ejer den trænede ML-model og er ansvarlig for at
generere ForecastResult-entiteter.

Domæneregler håndhæves her:
  - En model skal have træningsdata før den kan generere prognoser
  - predicted_count i ForecastResult er aldrig negativ

Event Storming kommandoer realiseret:
  - Træn Model       → ForecastModel.træn(training_data)
  - Generer Prognose → .forudsig(time_feature, price_features, historical_count)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from app.domain.value_objects.value_objects import (
    PriceFeatures,
    SessionCount,
    TimeFeature,
)


@dataclass
class ForecastResult:
    """
    Entitet: et konkret prognoseresultat produceret af ForecastModel.

    Felter (præcist som defineret i DDD-modellen):
        time_feature:       TimeFeature value object (hour_of_day, day_of_week)
        price_features:     PriceFeatures value object (spot_price)
        session_count:      SessionCount value object (historisk antal sessions)
        predicted_count:    forudsagt antal sessions (float fra ML-modellen)
        forecast_timestamp: hvornår prognosen blev genereret

    Event Storming event: 'Prognose Genereret'.
    """
    forecast_id: str
    model_id: str
    time_feature: TimeFeature
    price_features: PriceFeatures
    session_count: SessionCount
    predicted_count: float
    forecast_timestamp: datetime


@dataclass
class ForecastModel:
    """
    Aggregat-rod for Load Forecast Bounded Context.
    Wrapper om en trænet scikit-learn RandomForestRegressor.

    Invarianter:
      - Modellen skal være trænet før forudsig() kan kaldes.
      - predicted_count i ForecastResult er aldrig negativ (clampet til 0).

    Event Storming kommandoer:
      Træn Model        → ForecastModel.træn(training_data)  [factory]
      Generer Prognose  → .forudsig(time_feature, price_features, historical_count)
    """

    model_id: str
    trained_at: datetime
    r2_score: float
    training_samples: int
    _model: Any = field(repr=False)

    # ------------------------------------------------------------------
    # Factory-metode
    # ------------------------------------------------------------------

    @classmethod
    def træn(cls, training_data: List[Dict]) -> "ForecastModel":
        """
        Træner en RandomForestRegressor på historiske session-data.

        Args:
            training_data: liste af dicts med nøgler:
                           hour_of_day, day_of_week, spot_price, session_count

        Returns:
            Et færdigt ForecastModel-aggregat

        Raises:
            ValueError: hvis training_data er tom

        Event Storming command: 'Træn Model'.
        """
        if not training_data:
            raise ValueError("Kan ikke træne ForecastModel uden træningsdata")

        from sklearn.ensemble import RandomForestRegressor
        from sklearn.metrics import r2_score as sklearn_r2
        import numpy as np

        X = np.array([
            [d["hour_of_day"], d["day_of_week"], d["spot_price"]]
            for d in training_data
        ])
        y = np.array([d["session_count"] for d in training_data])

        model = RandomForestRegressor(n_estimators=50, random_state=42, max_depth=6)
        model.fit(X, y)

        score = float(sklearn_r2(y, model.predict(X)))

        return cls(
            model_id=str(uuid4()),
            trained_at=datetime.now(timezone.utc),
            r2_score=round(score, 4),
            training_samples=len(training_data),
            _model=model,
        )

    # ------------------------------------------------------------------
    # Domæne-metode
    # ------------------------------------------------------------------

    def forudsig(
        self,
        time_feature: TimeFeature,
        price_features: PriceFeatures,
        historical_count: SessionCount,
    ) -> ForecastResult:
        """
        Genererer en ForecastResult for de givne features.

        Args:
            time_feature:     TimeFeature (hour_of_day, day_of_week)
            price_features:   PriceFeatures (spot_price)
            historical_count: SessionCount (historisk baseline)

        Returns:
            ForecastResult med predicted_count ≥ 0

        Raises:
            ValueError: hvis modellen ikke er trænet

        Event Storming command: 'Generer Prognose'.
        """
        if self._model is None:
            raise ValueError("ForecastModel er ikke trænet — kald træn() først")

        import numpy as np

        X = np.array([[
            time_feature.hour_of_day,
            time_feature.day_of_week,
            price_features.spot_price,
        ]])

        raw = float(self._model.predict(X)[0])
        predicted = max(0.0, round(raw, 2))

        return ForecastResult(
            forecast_id=str(uuid4()),
            model_id=self.model_id,
            time_feature=time_feature,
            price_features=price_features,
            session_count=historical_count,
            predicted_count=predicted,
            forecast_timestamp=datetime.now(timezone.utc),
        )
