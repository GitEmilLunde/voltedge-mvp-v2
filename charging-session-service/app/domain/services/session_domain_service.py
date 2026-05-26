"""
Domæneservice — Charging Session Bounded Context.

Indeholder domænelogik der involverer FLERE aggregater eller
ikke naturligt hører hjemme på ét aggregat.

Aktuelt: beregning og validering af SessionCost på tværs af aggregater.
"""

from __future__ import annotations

from app.domain.value_objects.value_objects import (
    AppliedSpotPrice,
    EnergyDelivered,
    SessionCost,
)


class SessionDomainService:
    """
    Domæneservice der håndterer beregningslogik for sessioner.

    Regler håndhævet her (ikke i applikationslaget):
      - SessionCost = EnergyDelivered × AppliedSpotPrice (afrundet til 4 decimaler)
      - Begge input skal være positive tal
    """

    @staticmethod
    def beregn_session_cost(
        energy_delivered: EnergyDelivered,
        applied_spot_price: AppliedSpotPrice,
    ) -> SessionCost:
        """
        Beregner SessionCost ud fra leveret energi og låst spotpris.

        Formel: SessionCost = EnergyDelivered × AppliedSpotPrice

        Args:
            energy_delivered:  Leveret energi i kWh (≥ 0)
            applied_spot_price: Låst spotpris i DKK/kWh

        Returns:
            SessionCost i DKK

        Event Storming event: 'CHARGING_STOPPED' — beregnes ét enkelt sted.
        """
        cost = round(energy_delivered.value * applied_spot_price.value, 4)
        return SessionCost(value=cost)
