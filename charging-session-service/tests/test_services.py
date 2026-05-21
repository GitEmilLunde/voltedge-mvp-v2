"""
Unit tests for VoltEdge Charging Session domain services.
Alle tests kører isoleret — ingen database eller netværkskald.
"""
import sys
import os

# Sørg for at vi finder app-pakken uanset working directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.session_lifecycle import transition
from app.services.idle_fee_service import calculate_idle_fee
from app.services.cost_calculator import calculate_session_cost
from app.services.spot_price_service import get_spot_price


# ──────────────────────────────────────────────
# TILSTANDSMASKINE
# ──────────────────────────────────────────────

class TestSessionLifecycle:
    """Lovlige og ulovlige statusovergange."""

    # Lovlige overgange
    def test_pending_to_authorized(self):
        assert transition("PENDING", "AUTHORIZED") == "AUTHORIZED"

    def test_authorized_to_active(self):
        assert transition("AUTHORIZED", "ACTIVE") == "ACTIVE"

    def test_active_to_completed(self):
        assert transition("ACTIVE", "COMPLETED") == "COMPLETED"

    def test_active_to_faulted(self):
        assert transition("ACTIVE", "FAULTED") == "FAULTED"

    # Ulovlige overgange
    def test_pending_to_active_raises(self):
        with pytest.raises(ValueError):
            transition("PENDING", "ACTIVE")

    def test_pending_to_completed_raises(self):
        with pytest.raises(ValueError):
            transition("PENDING", "COMPLETED")

    def test_authorized_to_completed_raises(self):
        with pytest.raises(ValueError):
            transition("AUTHORIZED", "COMPLETED")

    def test_completed_to_active_raises(self):
        with pytest.raises(ValueError):
            transition("COMPLETED", "ACTIVE")

    def test_faulted_to_completed_raises(self):
        with pytest.raises(ValueError):
            transition("FAULTED", "COMPLETED")

    def test_completed_is_terminal(self):
        with pytest.raises(ValueError):
            transition("COMPLETED", "AUTHORIZED")


# ──────────────────────────────────────────────
# IDLE FEE
# ──────────────────────────────────────────────

class TestIdleFee:
    """Idle fee opkræves kun i spidstid og ved session > 3 timer."""

    def test_peak_over_3h_gives_fee(self):
        # 10:00 start, 4 timers session → fee
        start = datetime(2024, 6, 10, 10, 0)
        end = start + timedelta(hours=4)
        assert calculate_idle_fee(start, end) == 10.00

    def test_peak_under_3h_no_fee(self):
        # 10:00 start, 2 timers session → ingen fee
        start = datetime(2024, 6, 10, 10, 0)
        end = start + timedelta(hours=2)
        assert calculate_idle_fee(start, end) == 0.00

    def test_offpeak_over_3h_no_fee(self):
        # 22:00 start (udenfor spidstid), 5 timers session → ingen fee
        start = datetime(2024, 6, 10, 22, 0)
        end = start + timedelta(hours=5)
        assert calculate_idle_fee(start, end) == 0.00

    def test_exactly_180_minutes_no_fee(self):
        # Præcis 180 min = IKKE over grænsen
        start = datetime(2024, 6, 10, 9, 0)
        end = start + timedelta(minutes=180)
        assert calculate_idle_fee(start, end) == 0.00

    def test_181_minutes_in_peak_gives_fee(self):
        # 181 min i spidstid → fee
        start = datetime(2024, 6, 10, 9, 0)
        end = start + timedelta(minutes=181)
        assert calculate_idle_fee(start, end) == 10.00

    def test_start_at_peak_boundary_08(self):
        # Præcis 08:00 er spidstid
        start = datetime(2024, 6, 10, 8, 0)
        end = start + timedelta(hours=4)
        assert calculate_idle_fee(start, end) == 10.00

    def test_start_at_20_is_offpeak(self):
        # 20:00 er UDEN FOR spidstid (eksklusiv)
        start = datetime(2024, 6, 10, 20, 0)
        end = start + timedelta(hours=4)
        assert calculate_idle_fee(start, end) == 0.00

    def test_none_times_returns_zero(self):
        assert calculate_idle_fee(None, None) == 0.00


# ──────────────────────────────────────────────
# PRISBEREGNING
# ──────────────────────────────────────────────

class TestCostCalculator:
    """SessionCost = energy × spotpris + idle_fee."""

    def test_basic_calculation(self):
        # 10 kWh × 0.5 DKK/kWh + 0 = 5.0 DKK
        assert calculate_session_cost(10.0, 0.5, 0.0) == 5.0

    def test_with_idle_fee(self):
        # 10 kWh × 0.5 + 10 idle = 15.0 DKK
        assert calculate_session_cost(10.0, 0.5, 10.0) == 15.0

    def test_zero_energy_gives_idle_fee_only(self):
        assert calculate_session_cost(0.0, 0.5, 10.0) == 10.0

    def test_high_spot_price(self):
        # 50 kWh × 2.0 DKK/kWh = 100.0 DKK
        assert calculate_session_cost(50.0, 2.0, 0.0) == 100.0

    def test_none_energy_returns_zero(self):
        assert calculate_session_cost(None, 0.5, 0.0) == 0.00

    def test_none_spot_price_returns_zero(self):
        assert calculate_session_cost(10.0, None, 0.0) == 0.00

    def test_none_idle_fee_treated_as_zero(self):
        assert calculate_session_cost(10.0, 1.0, None) == 10.0


# ──────────────────────────────────────────────
# SPOTPRIS — FALLBACK
# ──────────────────────────────────────────────

class TestSpotPriceService:
    """Spotpristjenesten falder tilbage til cached pris ved API-fejl."""

    @patch("app.services.spot_price_service.requests.get")
    def test_api_success_converts_mwh_to_kwh(self, mock_get):
        session_hour = datetime(2024, 6, 10, 10, 0, 0)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "records": [{"TimeDK": session_hour.isoformat(), "SpotPriceDKK": 500.0}]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        price = get_spot_price("DK1", session_hour, "http://test.energi")
        assert price == pytest.approx(0.5)

    @patch("app.services.spot_price_service.requests.get")
    def test_api_failure_returns_last_known(self, mock_get):
        import requests as req
        import app.services.spot_price_service as svc

        svc._LAST_KNOWN_PRICE["DK1"] = 0.75
        mock_get.side_effect = req.RequestException("timeout")

        price = get_spot_price("DK1", datetime(2024, 6, 10, 10), "http://test.energi")
        assert price == 0.75

    @patch("app.services.spot_price_service.requests.get")
    def test_api_failure_default_fallback_when_no_cache(self, mock_get):
        import requests as req
        import app.services.spot_price_service as svc

        svc._LAST_KNOWN_PRICE.pop("DK2", None)
        mock_get.side_effect = req.RequestException("timeout")

        price = get_spot_price("DK2", datetime(2024, 6, 10, 10), "http://test.energi")
        assert price == pytest.approx(0.50)
