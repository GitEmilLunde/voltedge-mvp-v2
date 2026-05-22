from dataclasses import dataclass


@dataclass(frozen=True)
class EnergyMeasurement:
    """Måleraflæsning for en ladesession. Leveret energi er aldrig negativ."""
    meter_start: float
    meter_end: float

    def __post_init__(self):
        if self.meter_start < 0 or self.meter_end < 0:
            raise ValueError("Målerværdier kan ikke være negative")

    @property
    def delivered_kwh(self) -> float:
        return max(0.0, self.meter_end - self.meter_start)
