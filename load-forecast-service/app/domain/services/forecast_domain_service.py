"""
Domæneservice — Load Forecast Bounded Context.

Hjælper med at aggregere rå session-data til træningsvenligt format.
Logik der ikke naturligt hører til ForecastModel-aggregatet.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List


class ForecastDomainService:
    """
    Domæneservice der transformerer rå session-records
    til feature-dicts brugt ved træning af ForecastModel.
    """

    @staticmethod
    def aggreger_til_træningsdata(session_records: List[Dict]) -> List[Dict]:
        """
        Aggregerer afsluttede session-records til træningsdata.

        Grupperer sessions efter (hour_of_day, day_of_week) og
        tæller antallet pr. gruppe — dette er SessionCount.

        Args:
            session_records: liste af dicts med:
                             hour_of_day, day_of_week, spot_price, session_id

        Returns:
            Liste af dicts med:
                hour_of_day, day_of_week, spot_price, session_count

        Event Storming: brugt i 'Træn Model'-use case.
        """
        grupper: Dict[tuple, List[float]] = defaultdict(list)

        for record in session_records:
            nøgle = (record["hour_of_day"], record["day_of_week"])
            grupper[nøgle].append(record.get("spot_price", 1.25))

        træningsdata = []
        for (time, dag), priser in grupper.items():
            træningsdata.append({
                "hour_of_day":   time,
                "day_of_week":   dag,
                "spot_price":    round(sum(priser) / len(priser), 4),
                "session_count": len(priser),
            })

        return træningsdata
