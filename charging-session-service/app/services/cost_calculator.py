"""
Prisberegning for VoltEdge ladesessioner.

Formel:
  SessionCost = energy_delivered [kWh] × spot_price_dkk [DKK/kWh] + idle_fee [DKK]
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def calculate_session_cost(
    energy_delivered: Optional[float],
    spot_price_dkk: Optional[float],
    idle_fee: Optional[float],
) -> float:
    """
    Beregner samlet sessionspris i DKK.
    Returnerer 0.0 hvis energy_delivered eller spot_price_dkk mangler.
    """
    if energy_delivered is None or spot_price_dkk is None:
        logger.warning("Manglende energidata — sessionspris sættes til 0")
        return 0.00

    energy_cost = energy_delivered * spot_price_dkk
    total = round(energy_cost + (idle_fee or 0.00), 4)

    logger.info(
        "Sessionspris: %.4f kWh × %.4f DKK/kWh + %.2f DKK idle = %.4f DKK",
        energy_delivered, spot_price_dkk, idle_fee or 0.0, total
    )
    return total
