from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionCost:
    """Samlet pris for en ladesession. Uforanderlig efter beregning."""
    energy_cost_dkk: float
    idle_fee_dkk: float

    @property
    def total_dkk(self) -> float:
        return round(self.energy_cost_dkk + self.idle_fee_dkk, 4)

    @classmethod
    def calculate(cls, delivered_kwh: float, dkk_per_kwh: float, idle_fee_dkk: float) -> SessionCost:
        return cls(
            energy_cost_dkk=delivered_kwh * dkk_per_kwh,
            idle_fee_dkk=idle_fee_dkk,
        )
