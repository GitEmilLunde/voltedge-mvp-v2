"""
IdleFeePolicy: domænepolitik for idle-gebyrer ved VoltEdge ladesessioner.

Regel:
  - Sessioner der starter i spidstid (08:00–20:00) og varer > 3 timer
  → 10 minutters buffer (ingen gebyr)
  → Herefter: 1,50 DKK/min

  Ellers → 0,00 DKK

Gebyret kompenserer ladepunktsoperatøren når et køretøj optager
en lader længere end nødvendigt i travle timer.
"""
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class IdleFeePolicy:
    GRACE_MINUTES = 180     # 3 timers fri opladning
    BUFFER_MINUTES = 10     # 10 min til at hente bilen inden gebyret starter
    PEAK_START = 8          # 08:00 inklusiv
    PEAK_END = 20           # 20:00 eksklusiv
    FEE_PER_MINUTE = 1.50   # DKK/min

    def calculate(
        self,
        session_start: Optional[datetime],
        session_end: Optional[datetime],
    ) -> float:
        """Returnerer idle-gebyr i DKK baseret på starttidspunkt og varighed."""
        if not session_start or not session_end:
            return 0.00

        duration_minutes = (session_end - session_start).total_seconds() / 60
        is_peak = self.PEAK_START <= session_start.hour < self.PEAK_END
        idle_minutes = duration_minutes - self.GRACE_MINUTES - self.BUFFER_MINUTES

        if not is_peak or idle_minutes <= 0:
            return 0.00

        fee = round(idle_minutes * self.FEE_PER_MINUTE, 2)
        logger.info(
            "Idle gebyr: %.0f min × %.2f kr/min = %.2f DKK",
            idle_minutes, self.FEE_PER_MINUTE, fee,
        )
        return fee
