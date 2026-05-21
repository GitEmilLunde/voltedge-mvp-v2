"""
Idle fee domænelogik for VoltEdge ladesessioner.

Regel:
  - Hvis session_start_time er i 08:00–20:00 (spidstid)
    OG sessionens varighed er > 180 minutter (3 timers grace)
  → 10 minutters buffer (ingen fee i bufferzonen)
  → Herefter: 1,50 DKK/min
  Ellers → idle_fee = 0,00 DKK

Idle fee kompenserer ladepunktsoperatøren når et køretøj
optager en lader længere end nødvendigt i travle timer.
"""
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

IDLE_GRACE_MINUTES      = 180   # 3 timer fri opladning
IDLE_BUFFER_MINUTES     = 10    # 10 min buffer til at hente bilen
IDLE_PEAK_START         = 8     # 08:00 inklusiv
IDLE_PEAK_END           = 20    # 20:00 eksklusiv
IDLE_FEE_PER_MINUTE     = 1.50  # kr/min


def calculate_idle_fee(
    session_start_time: Optional[datetime],
    session_end_time: Optional[datetime],
) -> float:
    """
    Returnerer idle fee i DKK baseret på starttidspunkt og varighed.
    """
    if not session_start_time or not session_end_time:
        return 0.00

    duration_minutes = (session_end_time - session_start_time).total_seconds() / 60
    start_hour = session_start_time.hour

    is_peak = IDLE_PEAK_START <= start_hour < IDLE_PEAK_END
    idle_minutes = duration_minutes - IDLE_GRACE_MINUTES - IDLE_BUFFER_MINUTES

    if not is_peak or idle_minutes <= 0:
        logger.debug(
            "Ingen idle fee: spidstid=%s, idle_min=%.1f",
            is_peak, max(idle_minutes, 0),
        )
        return 0.00

    fee = round(idle_minutes * IDLE_FEE_PER_MINUTE, 2)

    logger.info(
        "Idle fee opkrævet: %.0f min idle × %.2f kr/min = %.2f DKK",
        idle_minutes, IDLE_FEE_PER_MINUTE, fee,
    )
    return fee
