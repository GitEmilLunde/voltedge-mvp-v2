"""
ForecastRepository — MySQL-persistering for Load Forecast Bounded Context.

Gemmer ForecastResult-entiteter i forecast_db.
ForecastModel er in-memory (ML-model serialiseres ikke til DB i MVP).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.domain.aggregates.forecast_model import ForecastResult
from app.domain.value_objects.value_objects import (
    PriceFeatures,
    SessionCount,
    TimeFeature,
)

logger = logging.getLogger(__name__)


class ForecastRepository:
    """
    Konkret repository der persisterer ForecastResult-entiteter i MySQL.

    Metoder:
        gem_resultat  — INSERT et ForecastResult
        hent_alle     — SELECT alle ForecastResults
        hent_seneste  — SELECT det seneste ForecastResult
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def gem_resultat(self, result: ForecastResult) -> None:
        """Persisterer et ForecastResult i forecast_results-tabellen."""
        with self._engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO forecast_results
                        (forecast_id, model_id, hour_of_day, day_of_week,
                         spot_price, session_count, predicted_count, forecast_timestamp)
                    VALUES
                        (:forecast_id, :model_id, :hour_of_day, :day_of_week,
                         :spot_price, :session_count, :predicted_count, :forecast_timestamp)
                """),
                {
                    "forecast_id":        result.forecast_id,
                    "model_id":           result.model_id,
                    "hour_of_day":        result.time_feature.hour_of_day,
                    "day_of_week":        result.time_feature.day_of_week,
                    "spot_price":         result.price_features.spot_price,
                    "session_count":      result.session_count.value,
                    "predicted_count":    result.predicted_count,
                    "forecast_timestamp": result.forecast_timestamp,
                },
            )

    def hent_alle(self) -> List[ForecastResult]:
        """Henter alle ForecastResults sorteret nyest først."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM forecast_results "
                    "ORDER BY forecast_timestamp DESC"
                )
            ).mappings().all()
            return [self._map(dict(r)) for r in rows]

    def hent_seneste(self) -> Optional[ForecastResult]:
        """Henter det seneste ForecastResult eller None."""
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM forecast_results "
                    "ORDER BY forecast_timestamp DESC LIMIT 1"
                )
            ).mappings().first()
            return self._map(dict(row)) if row else None

    # ------------------------------------------------------------------
    # Privat hjælpemetode
    # ------------------------------------------------------------------

    @staticmethod
    def _map(row: dict) -> ForecastResult:
        """Mapper en database-række til et ForecastResult-objekt."""
        ts = row["forecast_timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)

        return ForecastResult(
            forecast_id=row["forecast_id"],
            model_id=row["model_id"],
            time_feature=TimeFeature(
                hour_of_day=int(row["hour_of_day"]),
                day_of_week=int(row["day_of_week"]),
            ),
            price_features=PriceFeatures(spot_price=float(row["spot_price"])),
            session_count=SessionCount(value=int(row["session_count"])),
            predicted_count=float(row["predicted_count"]),
            forecast_timestamp=ts,
        )
