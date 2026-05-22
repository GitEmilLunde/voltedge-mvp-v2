"""
ChargingSession — aggregate root for VoltEdge's opladnings-bounded context.

Invarianter:
  - Status følger den tilladte tilstandsmaskine:
      PENDING → AUTHORIZED → ACTIVE → COMPLETED | FAULTED
  - Spotpris låses ved oprettelse og ændres aldrig
  - Energilevering = max(0, meter_end - meter_start)
  - SessionCost = energiomkostning + idle_fee
"""
import uuid
from datetime import datetime

from app.extensions import db
from app.domain.value_objects import EnergyMeasurement, SessionCost
from app.domain.services.session_lifecycle import transition
from app.domain.services.idle_fee_policy import IdleFeePolicy


class SessionNotFound(Exception):
    pass


class ChargingSession(db.Model):
    __tablename__ = "charging_sessions"

    # ─── Identitet ──────────────────────────────────────────────
    session_id = db.Column(
        db.String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # ─── Kerneatributter ────────────────────────────────────────
    charger_id   = db.Column(db.String(50), nullable=False)
    connector_id = db.Column(db.String(50), nullable=False)
    contract_id  = db.Column(db.String(50), nullable=False)
    price_area   = db.Column(db.Enum("DK1", "DK2"), nullable=False)

    # ─── Livscyklus ─────────────────────────────────────────────
    status = db.Column(
        db.Enum("PENDING", "AUTHORIZED", "ACTIVE", "COMPLETED", "FAULTED"),
        default="PENDING",
    )
    session_start_time = db.Column(db.DateTime)
    session_end_time   = db.Column(db.DateTime)
    stop_reason        = db.Column(db.Enum("Normal", "Timeout", "Fault", "Administrative"))

    # ─── Energi og pris (spotpris låst ved sessionstart) ────────
    meter_start      = db.Column(db.Float)
    meter_end        = db.Column(db.Float)
    energy_delivered = db.Column(db.Float)
    spot_price_dkk   = db.Column(db.Float)
    idle_fee         = db.Column(db.Float)
    session_cost     = db.Column(db.Float)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ─── Domæneadfærd ───────────────────────────────────────────

    def authorize(self) -> None:
        """PENDING → AUTHORIZED."""
        self.status = transition(self.status, "AUTHORIZED")

    def activate(self, meter_start: float) -> None:
        """AUTHORIZED → ACTIVE. Registrerer startmålerstand."""
        self.status = transition(self.status, "ACTIVE")
        self.meter_start = meter_start

    def complete(self, meter_end: float, idle_fee_policy: IdleFeePolicy) -> SessionCost:
        """ACTIVE → COMPLETED. Beregner og returnerer den endelige SessionCost."""
        self.status = transition(self.status, "COMPLETED")
        self.session_end_time = datetime.utcnow()
        self.meter_end = meter_end

        energy = EnergyMeasurement(self.meter_start or 0.0, meter_end)
        idle_fee_dkk = idle_fee_policy.calculate(self.session_start_time, self.session_end_time)
        cost = SessionCost.calculate(energy.delivered_kwh, self.spot_price_dkk or 0.0, idle_fee_dkk)

        self.energy_delivered = energy.delivered_kwh
        self.idle_fee = cost.idle_fee_dkk
        self.session_cost = cost.total_dkk

        return cost

    def fault(self, reason: str = "Fault") -> None:
        """ACTIVE → FAULTED. Registrerer fejl og afslutter sessionen."""
        self.status = transition(self.status, "FAULTED")
        self.session_end_time = datetime.utcnow()
        self.stop_reason = reason

    # ─── Serialisering ──────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "session_id":         self.session_id,
            "charger_id":         self.charger_id,
            "connector_id":       self.connector_id,
            "contract_id":        self.contract_id,
            "price_area":         self.price_area,
            "status":             self.status,
            "session_start_time": self.session_start_time.isoformat() if self.session_start_time else None,
            "session_end_time":   self.session_end_time.isoformat()   if self.session_end_time   else None,
            "meter_start":        self.meter_start,
            "meter_end":          self.meter_end,
            "energy_delivered":   self.energy_delivered,
            "spot_price_dkk":     self.spot_price_dkk,
            "idle_fee":           self.idle_fee,
            "session_cost":       self.session_cost,
            "stop_reason":        self.stop_reason,
            "created_at":         self.created_at.isoformat() if self.created_at else None,
        }
