"""
Ekstern adapter — henter afsluttede session-data fra charging-session-service.

Anti-korruptionslag: load-forecast-service importerer ALDRIG direkte fra
charging-session-service. Al kommunikation sker via HTTP REST API.

Henter kun AFSLUTTET-sessions — kun disse har EnergyDelivered og SessionCost.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List

import requests

logger = logging.getLogger(__name__)

_FALLBACK_DATA = [
    {"hour_of_day": h, "day_of_week": d, "spot_price": 1.25, "session_id": f"fallback-{h}-{d}"}
    for h in range(0, 24, 2)
    for d in range(1, 8)
]


class SessionDataClient:
    """
    HTTP-klient der henter session-data fra charging-session-service.
    Bruges som input til ForecastModel-træning.

    Anti-korruption: returnerer plain dicts — ingen domain-typer fra charging BC.
    """

    def __init__(self, base_url: str, timeout_sek: int = 10) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_sek

    def hent_afsluttede_sessions(self) -> List[Dict]:
        """
        Henter alle AFSLUTTET-sessions fra charging-session-service.
        Filtrerer og mapper kun de felter ForecastModel har brug for.

        Returns:
            Liste af dicts med: hour_of_day, day_of_week, spot_price, session_id

        Ved fejl returneres syntetisk fallback-data.
        """
        try:
            resp = requests.get(
                f"{self._base_url}/sessions",
                timeout=self._timeout,
            )
            resp.raise_for_status()
            alle_sessions = resp.json()

            afsluttede = [s for s in alle_sessions if s.get("status") == "AFSLUTTET"]

            if not afsluttede:
                logger.warning(
                    "Ingen AFSLUTTET-sessions fra charging-session-service — bruger fallback"
                )
                return _FALLBACK_DATA

            return [self._map_session(s) for s in afsluttede]

        except requests.RequestException as exc:
            logger.error(
                "Fejl ved hentning af sessions fra charging-session-service: %s — bruger fallback",
                exc,
            )
            return _FALLBACK_DATA

    # ------------------------------------------------------------------
    # Privat hjælpemetode
    # ------------------------------------------------------------------

    @staticmethod
    def _map_session(session: Dict) -> Dict:
        """
        Mapper én session til et feature-dict.
        Udtrækker kun de felter domænet har brug for.
        """
        start_time = session.get("start_time")
        hour = 12
        dow = 1

        if start_time:
            try:
                dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                hour = dt.hour
                dow = dt.isoweekday()  # 1 = mandag, 7 = søndag
            except (ValueError, AttributeError):
                pass

        return {
            "session_id":   session.get("session_id", ""),
            "hour_of_day":  hour,
            "day_of_week":  dow,
            "spot_price":   session.get("applied_spot_price") or 1.25,
        }
