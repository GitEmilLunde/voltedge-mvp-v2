"""
Idle fee domænelogik for VoltEdge ladesessioner.

Regel:
  - Hvis session_start_time er i 08:00–20:00 (spidstid)
    OG sessionens varighed er > 180 minutter
  → idle_fee = 10,00 DKK
  Ellers → idle_fee = 0,00 DKK

Idle fee kompenserer ladepunktsoperatøren når et køretøj
optager en lader længere end nødvendigt i travle timer.
"""
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

IDLE_FEE_AMOUNT   = 10.00   # DKK
PEAK_START_HOUR   = 8       # 08:00 inklusiv
PEAK_END_HOUR     = 20      # 20:00 eksklusiv
MAX_FREE_MINUTES  = 180     # grænse: > 180 min giver fee


def calculate_idle_fee(
    session_start_time: Optional[datetime],
    session_end_time: Optional[datetime]
) -> float:
    """
    Returnerer idle fee i DKK baseret på starttidspunkt og varighed.
    """
    if not session_start_time or not session_end_time:
        return 0.00

    duration_minutes = (session_end_time - session_start_time).total_seconds() / 60
    start_hour = session_start_time.hour

    is_peak = PEAK_START_HOUR <= start_hour < PEAK_END_HOUR
    is_long = duration_minutes > MAX_FREE_MINUTES

    if is_peak and is_long:
        logger.info(
            "Idle fee opkrævet: start=%02d:00 (spidstid), varighed=%.0f min > %d min",
            start_hour, duration_minutes, MAX_FREE_MINUTES
        )
        return IDLE_FEE_AMOUNT

    logger.debug(
        "Ingen idle fee: spidstid=%s, lang_session=%s, varighed=%.0f min",
        is_peak, is_long, duration_minutes
    )
    return 0.00
