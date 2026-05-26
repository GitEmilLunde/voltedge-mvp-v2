"""
Applikationsservice — Load Forecast Bounded Context.

Orkestrerer use cases:
  - træn_model       — henter session-data og træner ForecastModel
  - generer_prognose — genererer og persisterer et ForecastResult
  - hent_prognoser   — returnerer alle gemte ForecastResults
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.domain.aggregates.forecast_model import ForecastModel, ForecastResult
from app.domain.services.forecast_domain_service import ForecastDomainService
from app.domain.value_objects.value_objects import (
    PriceFeatures,
    SessionCount,
    TimeFeature,
)
from app.infrastructure.external.session_data_client import SessionDataClient
from app.infrastructure.repositories.forecast_repository import ForecastRepository

logger = logging.getLogger(__name__)


class ForecastApplicationService:
    """
    Applikationsservice der orkestrerer alle use cases for Load Forecast BC.

    Afhænger af:
        ForecastRepository  — persistering af ForecastResults
        SessionDataClient   — hentning af historisk session-data
    """

    def __init__(
        self,
        repository: ForecastRepository,
        session_data_client: SessionDataClient,
    ) -> None:
        self._repo = repository
        self._session_client = session_data_client
        self._aktiv_model: Optional[ForecastModel] = None

    # ------------------------------------------------------------------
    # Use cases
    # ------------------------------------------------------------------

    def træn_model(self) -> ForecastModel:
        """
        Henter afsluttede sessions fra charging-session-service,
        aggregerer til træningsdata og træner en ny ForecastModel.

        Returns:
            Det trænede ForecastModel-aggregat

        Event Storming command: 'Træn Model'.
        """
        rå_data = self._session_client.hent_afsluttede_sessions()
        træningsdata = ForecastDomainService.aggreger_til_træningsdata(rå_data)

        model = ForecastModel.træn(træningsdata)
        self._aktiv_model = model

        logger.info(
            "ForecastModel trænet: %s, R²=%.4f, samples=%d",
            model.model_id,
            model.r2_score,
            model.training_samples,
        )
        return model

    def generer_prognose(
        self,
        hour_of_day: int,
        day_of_week: int,
        spot_price: float,
    ) -> ForecastResult:
        """
        Genererer en prognose for det givne tidspunkt og pris.
        Træner modellen automatisk første gang den kaldes.

        Args:
            hour_of_day: time på dagen (0–23)
            day_of_week: ugedag (1–7, 1 = mandag)
            spot_price:  spotpris i DKK/kWh

        Returns:
            ForecastResult med predicted_count

        Event Storming command: 'Generer Prognose'.
        """
        if self._aktiv_model is None:
            logger.info("Ingen aktiv model — træner automatisk")
            self.træn_model()

        time_feature = TimeFeature(hour_of_day=hour_of_day, day_of_week=day_of_week)
        price_features = PriceFeatures(spot_price=spot_price)

        historisk_count = self._beregn_historisk_count(hour_of_day, day_of_week)

        result = self._aktiv_model.forudsig(time_feature, price_features, historisk_count)
        self._repo.gem_resultat(result)

        logger.info(
            "Prognose genereret: time=%d, dag=%d, pris=%.4f → forudsagt=%.2f",
            hour_of_day, day_of_week, spot_price, result.predicted_count,
        )
        return result

    def hent_prognoser(self) -> List[ForecastResult]:
        """Returnerer alle gemte ForecastResults."""
        return self._repo.hent_alle()

    def hent_model_info(self) -> Optional[dict]:
        """Returnerer metadata om den aktive model, eller None."""
        if self._aktiv_model is None:
            return None
        return {
            "model_id":         self._aktiv_model.model_id,
            "trained_at":       self._aktiv_model.trained_at.isoformat(),
            "r2_score":         self._aktiv_model.r2_score,
            "training_samples": self._aktiv_model.training_samples,
        }

    # ------------------------------------------------------------------
    # Privat hjælpemetode
    # ------------------------------------------------------------------

    def _beregn_historisk_count(self, hour_of_day: int, day_of_week: int) -> SessionCount:
        """
        Beregner historisk SessionCount for det givne tidspunkt.
        Tæller tidligere ForecastResults med samme time og dag.
        """
        alle = self._repo.hent_alle()
        tælling = sum(
            1 for r in alle
            if r.time_feature.hour_of_day == hour_of_day
            and r.time_feature.day_of_week == day_of_week
        )
        return SessionCount(value=tælling)
