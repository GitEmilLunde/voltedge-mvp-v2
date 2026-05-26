"""
Tests — Load Forecast Bounded Context.

Tester value object invarianter, ForecastModel-aggregat og API endpoints.
Ingen databaseforbindelse eller ekstern HTTP påkrævet.
"""

import pytest
from unittest.mock import MagicMock

from app.domain.aggregates.forecast_model import ForecastModel, ForecastResult
from app.domain.services.forecast_domain_service import ForecastDomainService
from app.domain.value_objects.value_objects import (
    PriceFeatures,
    SessionCount,
    TimeFeature,
)


# ---------------------------------------------------------------------------
# Value Object invarianter
# ---------------------------------------------------------------------------

class TestTimeFeature:

    def test_gyldig_time_feature(self):
        tf = TimeFeature(hour_of_day=14, day_of_week=3)
        assert tf.hour_of_day == 14
        assert tf.day_of_week == 3

    def test_ugyldig_time_over_23(self):
        with pytest.raises(ValueError, match="hour_of_day"):
            TimeFeature(hour_of_day=24, day_of_week=1)

    def test_ugyldig_time_negativ(self):
        with pytest.raises(ValueError, match="hour_of_day"):
            TimeFeature(hour_of_day=-1, day_of_week=1)

    def test_dag_0_er_ugyldig(self):
        with pytest.raises(ValueError, match="day_of_week"):
            TimeFeature(hour_of_day=10, day_of_week=0)

    def test_dag_8_er_ugyldig(self):
        with pytest.raises(ValueError, match="day_of_week"):
            TimeFeature(hour_of_day=10, day_of_week=8)

    def test_dag_1_til_7_er_gyldige(self):
        for dag in range(1, 8):
            tf = TimeFeature(hour_of_day=12, day_of_week=dag)
            assert tf.day_of_week == dag

    def test_time_feature_er_frozen(self):
        tf = TimeFeature(hour_of_day=10, day_of_week=2)
        with pytest.raises((AttributeError, TypeError)):
            tf.hour_of_day = 15  # type: ignore


class TestSessionCount:

    def test_gyldig_session_count(self):
        sc = SessionCount(value=5)
        assert sc.value == 5

    def test_nul_er_tilladt(self):
        sc = SessionCount(value=0)
        assert sc.value == 0

    def test_negativ_er_ikke_tilladt(self):
        with pytest.raises(ValueError, match="negativ"):
            SessionCount(value=-1)

    def test_session_count_er_frozen(self):
        sc = SessionCount(value=3)
        with pytest.raises((AttributeError, TypeError)):
            sc.value = 10  # type: ignore


class TestPriceFeatures:

    def test_gyldig_price_features(self):
        pf = PriceFeatures(spot_price=1.42)
        assert pf.spot_price == 1.42

    def test_price_features_er_frozen(self):
        pf = PriceFeatures(spot_price=1.0)
        with pytest.raises((AttributeError, TypeError)):
            pf.spot_price = 2.0  # type: ignore


# ---------------------------------------------------------------------------
# ForecastModel — træning og forudsigelse
# ---------------------------------------------------------------------------

def _byg_træningsdata(antal: int = 30):
    """Genererer minimalt realistisk træningsdata."""
    import random
    data = []
    for _ in range(antal):
        data.append({
            "hour_of_day":   random.randint(0, 23),
            "day_of_week":   random.randint(1, 7),
            "spot_price":    round(random.uniform(0.5, 2.5), 2),
            "session_count": random.randint(0, 10),
        })
    return data


class TestForecastModel:

    def test_træn_returnerer_forecast_model(self):
        data = _byg_træningsdata(50)
        model = ForecastModel.træn(data)
        assert isinstance(model, ForecastModel)
        assert model.model_id is not None
        assert model.training_samples == 50

    def test_r2_score_er_mellem_minus_et_og_en(self):
        data = _byg_træningsdata(50)
        model = ForecastModel.træn(data)
        assert -1.0 <= model.r2_score <= 1.0

    def test_træn_med_tom_data_hæver_value_error(self):
        with pytest.raises(ValueError, match="træningsdata"):
            ForecastModel.træn([])

    def test_forudsig_returnerer_forecast_result(self):
        model = ForecastModel.træn(_byg_træningsdata(40))
        result = model.forudsig(
            time_feature=TimeFeature(hour_of_day=17, day_of_week=2),
            price_features=PriceFeatures(spot_price=1.50),
            historical_count=SessionCount(value=3),
        )
        assert isinstance(result, ForecastResult)
        assert result.predicted_count >= 0
        assert result.model_id == model.model_id

    def test_predicted_count_er_aldrig_negativ(self):
        """Invariant: predicted_count ≥ 0 — clampet i aggregatet."""
        model = ForecastModel.træn(_byg_træningsdata(50))
        for _ in range(10):
            result = model.forudsig(
                time_feature=TimeFeature(hour_of_day=3, day_of_week=7),
                price_features=PriceFeatures(spot_price=0.01),
                historical_count=SessionCount(value=0),
            )
            assert result.predicted_count >= 0

    def test_to_modeller_har_forskellige_model_ids(self):
        data = _byg_træningsdata(30)
        m1 = ForecastModel.træn(data)
        m2 = ForecastModel.træn(data)
        assert m1.model_id != m2.model_id


# ---------------------------------------------------------------------------
# ForecastDomainService
# ---------------------------------------------------------------------------

class TestForecastDomainService:

    def test_aggreger_tom_liste_giver_tom_liste(self):
        result = ForecastDomainService.aggreger_til_træningsdata([])
        assert result == []

    def test_aggreger_grupper_korrekt(self):
        records = [
            {"hour_of_day": 8, "day_of_week": 1, "spot_price": 1.0},
            {"hour_of_day": 8, "day_of_week": 1, "spot_price": 1.5},
            {"hour_of_day": 17, "day_of_week": 3, "spot_price": 2.0},
        ]
        result = ForecastDomainService.aggreger_til_træningsdata(records)
        # Skal producere 2 grupper
        assert len(result) == 2

    def test_session_count_er_korrekt_aggregeret(self):
        records = [
            {"hour_of_day": 10, "day_of_week": 2, "spot_price": 1.0},
            {"hour_of_day": 10, "day_of_week": 2, "spot_price": 1.2},
            {"hour_of_day": 10, "day_of_week": 2, "spot_price": 0.8},
        ]
        result = ForecastDomainService.aggreger_til_træningsdata(records)
        assert len(result) == 1
        assert result[0]["session_count"] == 3

    def test_spot_price_er_gennemsnit_af_gruppen(self):
        records = [
            {"hour_of_day": 14, "day_of_week": 5, "spot_price": 1.0},
            {"hour_of_day": 14, "day_of_week": 5, "spot_price": 3.0},
        ]
        result = ForecastDomainService.aggreger_til_træningsdata(records)
        assert result[0]["spot_price"] == 2.0


# ---------------------------------------------------------------------------
# API-tests — load-forecast-service
# ---------------------------------------------------------------------------

class TestForecastAPI:

    @pytest.fixture
    def client(self):
        from unittest.mock import MagicMock
        from flask import Flask
        from app.application.forecast_application_service import ForecastApplicationService
        from app.presentation.routes import create_blueprint
        from datetime import datetime, timezone

        mock_service = MagicMock(spec=ForecastApplicationService)
        app = Flask(__name__)
        bp = create_blueprint(mock_service)
        app.register_blueprint(bp)
        app.config["TESTING"] = True

        with app.test_client() as c:
            yield c, mock_service

    def test_health_check(self, client):
        c, _ = client
        resp = c.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_forudsig_returnerer_201(self, client):
        from datetime import datetime, timezone
        c, svc = client

        svc.generer_prognose.return_value = ForecastResult(
            forecast_id="forecast-001",
            model_id="model-001",
            time_feature=TimeFeature(hour_of_day=14, day_of_week=3),
            price_features=PriceFeatures(spot_price=1.50),
            session_count=SessionCount(value=2),
            predicted_count=4.5,
            forecast_timestamp=datetime.now(timezone.utc),
        )

        resp = c.post("/forecast/forudsig", json={
            "hour_of_day": 14,
            "day_of_week": 3,
            "spot_price":  1.50,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["predicted_count"] == 4.5

    def test_forudsig_manglende_felt_returnerer_400(self, client):
        c, _ = client
        resp = c.post("/forecast/forudsig", json={"hour_of_day": 14})
        assert resp.status_code == 400

    def test_hent_prognoser_returnerer_liste(self, client):
        c, svc = client
        svc.hent_prognoser.return_value = []
        resp = c.get("/forecast")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_model_info_returnerer_404_når_ingen_model(self, client):
        c, svc = client
        svc.hent_model_info.return_value = None
        resp = c.get("/forecast/model")
        assert resp.status_code == 404
