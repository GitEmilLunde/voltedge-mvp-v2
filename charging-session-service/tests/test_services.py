"""
Unit tests for VoltEdge Charging Session domænelag.
Alle tests kører isoleret — ingen database eller netværkskald.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.domain.services.session_lifecycle import transition
from app.domain.services.idle_fee_policy import IdleFeePolicy
from app.domain.value_objects.session_cost import SessionCost
from app.infrastructure.external.spot_price_client import SpotPriceClient


# ──────────────────────────────────────────────
# TILSTANDSMASKINE
# ──────────────────────────────────────────────

class TestSessionLifecycle:
    """Lovlige og ulovlige statusovergange."""

    def test_pending_to_authorized(self):
        assert transition("PENDING", "AUTHORIZED") == "AUTHORIZED"

    def test_authorized_to_active(self):
        assert transition("AUTHORIZED", "ACTIVE") == "ACTIVE"

    def test_active_to_completed(self):
        assert transition("ACTIVE", "COMPLETED") == "COMPLETED"

    def test_active_to_faulted(self):
        assert transition("ACTIVE", "FAULTED") == "FAULTED"

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
# IDLE FEE POLICY
# ──────────────────────────────────────────────

class TestIdleFeePolicy:
    """Idle-gebyr: per-minut efter 3t grace + 10 min buffer, kun i spidstid."""

    def setup_method(self):
        self.policy = IdleFeePolicy()

    def test_peak_over_3h_gives_fee(self):
        # 4t session: 240 - 180 grace - 10 buffer = 50 min idle → 50 × 1.50 = 75.00 DKK
        start = datetime(2024, 6, 10, 10, 0)
        end = start + timedelta(hours=4)
        assert self.policy.calculate(start, end) == pytest.approx(75.00)

    def test_peak_under_3h_no_fee(self):
        start = datetime(2024, 6, 10, 10, 0)
        end = start + timedelta(hours=2)
        assert self.policy.calculate(start, end) == 0.00

    def test_offpeak_over_3h_no_fee(self):
        start = datetime(2024, 6, 10, 22, 0)
        end = start + timedelta(hours=5)
        assert self.policy.calculate(start, end) == 0.00

    def test_exactly_180_minutes_no_fee(self):
        start = datetime(2024, 6, 10, 9, 0)
        end = start + timedelta(minutes=180)
        assert self.policy.calculate(start, end) == 0.00

    def test_181_minutes_in_buffer_no_fee(self):
        start = datetime(2024, 6, 10, 9, 0)
        end = start + timedelta(minutes=181)
        assert self.policy.calculate(start, end) == 0.00

    def test_191_minutes_in_peak_gives_fee(self):
        # 191 min = 1 min idle → 1 × 1.50 = 1.50 DKK
        start = datetime(2024, 6, 10, 9, 0)
        end = start + timedelta(minutes=191)
        assert self.policy.calculate(start, end) == pytest.approx(1.50)

    def test_start_at_peak_boundary_08(self):
        start = datetime(2024, 6, 10, 8, 0)
        end = start + timedelta(hours=4)
        assert self.policy.calculate(start, end) == pytest.approx(75.00)

    def test_start_at_20_is_offpeak(self):
        start = datetime(2024, 6, 10, 20, 0)
        end = start + timedelta(hours=4)
        assert self.policy.calculate(start, end) == 0.00

    def test_none_times_returns_zero(self):
        assert self.policy.calculate(None, None) == 0.00


# ──────────────────────────────────────────────
# SESSION COST
# ──────────────────────────────────────────────

class TestSessionCost:
    """SessionCost = energy × spotpris + idle_fee."""

    def test_basic_calculation(self):
        cost = SessionCost.calculate(10.0, 0.5, 0.0)
        assert cost.total_dkk == 5.0

    def test_with_idle_fee(self):
        cost = SessionCost.calculate(10.0, 0.5, 10.0)
        assert cost.total_dkk == 15.0

    def test_zero_energy_gives_idle_fee_only(self):
        cost = SessionCost.calculate(0.0, 0.5, 10.0)
        assert cost.total_dkk == 10.0

    def test_high_spot_price(self):
        cost = SessionCost.calculate(50.0, 2.0, 0.0)
        assert cost.total_dkk == 100.0

    def test_energy_cost_and_idle_fee_are_accessible(self):
        cost = SessionCost.calculate(10.0, 1.0, 5.0)
        assert cost.energy_cost_dkk == pytest.approx(10.0)
        assert cost.idle_fee_dkk == pytest.approx(5.0)
        assert cost.total_dkk == pytest.approx(15.0)

    def test_immutability(self):
        cost = SessionCost.calculate(10.0, 0.5, 0.0)
        with pytest.raises(Exception):
            cost.energy_cost_dkk = 99.0  # frozen dataclass


# ──────────────────────────────────────────────
# SPOT PRICE CLIENT — FALLBACK
# ──────────────────────────────────────────────

class TestSpotPriceClient:
    """SpotPriceClient falder tilbage til cached pris ved API-fejl."""

    @patch("app.infrastructure.external.spot_price_client.requests.get")
    def test_api_success_converts_mwh_to_kwh(self, mock_get):
        session_hour = datetime(2024, 6, 10, 10, 0, 0)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "records": [{"TimeDK": session_hour.isoformat(), "SpotPriceDKK": 500.0}]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        client = SpotPriceClient("http://test.energi")
        price = client.fetch("DK1", session_hour)
        assert price.dkk_per_kwh == pytest.approx(0.5)
        assert price.price_area == "DK1"

    @patch("app.infrastructure.external.spot_price_client.requests.get")
    def test_api_failure_returns_last_known(self, mock_get):
        import requests as req
        mock_get.side_effect = req.RequestException("timeout")

        client = SpotPriceClient("http://test.energi")
        client._cache["DK1"] = 0.75

        price = client.fetch("DK1", datetime(2024, 6, 10, 10))
        assert price.dkk_per_kwh == pytest.approx(0.75)

    @patch("app.infrastructure.external.spot_price_client.requests.get")
    def test_api_failure_default_fallback_when_no_cache(self, mock_get):
        import requests as req
        mock_get.side_effect = req.RequestException("timeout")

        client = SpotPriceClient("http://test.energi")
        price = client.fetch("DK2", datetime(2024, 6, 10, 10))
        assert price.dkk_per_kwh == pytest.approx(0.50)
