import uuid
from datetime import datetime
from . import db


class ChargingSession(db.Model):
    __tablename__ = "charging_sessions"

    session_id = db.Column(
        db.String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    charger_id    = db.Column(db.String(50), nullable=False)
    connector_id  = db.Column(db.String(50), nullable=False)
    contract_id   = db.Column(db.String(50), nullable=False)
    charger_type  = db.Column(db.Enum("fast", "normal"), nullable=False)
    price_area    = db.Column(db.Enum("DK1", "DK2"), nullable=False)
    status        = db.Column(
        db.Enum("PENDING", "AUTHORIZED", "ACTIVE", "COMPLETED", "FAULTED"),
        default="PENDING"
    )
    session_start_time = db.Column(db.DateTime)
    session_end_time   = db.Column(db.DateTime)
    meter_start        = db.Column(db.Float)
    meter_end          = db.Column(db.Float)
    energy_delivered   = db.Column(db.Float)   # meter_end - meter_start
    spot_price_dkk     = db.Column(db.Float)   # låst ved sessionstart
    idle_fee           = db.Column(db.Float)   # 0 eller 10 DKK
    session_cost       = db.Column(db.Float)   # energy × pris + idle_fee
    stop_reason        = db.Column(
        db.Enum("Normal", "Timeout", "Fault", "Administrative")
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "session_id":         self.session_id,
            "charger_id":         self.charger_id,
            "connector_id":       self.connector_id,
            "contract_id":        self.contract_id,
            "charger_type":       self.charger_type,
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
