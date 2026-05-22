from dataclasses import dataclass


@dataclass(frozen=True)
class SpotPrice:
    """Spotpris låst ved sessionstart. Uforanderlig — ændres aldrig efter oprettelse."""
    price_area: str
    dkk_per_kwh: float

    def __post_init__(self):
        if self.dkk_per_kwh < 0:
            raise ValueError(f"Spotpris kan ikke være negativ: {self.dkk_per_kwh}")
