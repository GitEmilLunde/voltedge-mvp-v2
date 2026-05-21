import uuid
from datetime import datetime
from . import db


class ForecastResult(db.Model):
    __tablename__ = "forecast_results"

    forecast_id              = db.Column(db.String(36), primary_key=True,
                                         default=lambda: str(uuid.uuid4()))
    charger_id               = db.Column(db.String(50), nullable=False)
    generated_at             = db.Column(db.DateTime, default=datetime.utcnow)
    prediction_window_hours  = db.Column(db.Integer, default=24)
    load_index               = db.Column(db.Float)
    temperature              = db.Column(db.Float)
    wind_speed               = db.Column(db.Float)
    spot_price_forecast      = db.Column(db.Float)
    historical_session_volume = db.Column(db.Integer)

    def to_dict(self):
        return {
            "forecast_id":               self.forecast_id,
            "charger_id":                self.charger_id,
            "generated_at":              self.generated_at.isoformat() if self.generated_at else None,
            "prediction_window_hours":   self.prediction_window_hours,
            "load_index":                self.load_index,
            "temperature":               self.temperature,
            "wind_speed":                self.wind_speed,
            "spot_price_forecast":       self.spot_price_forecast,
            "historical_session_volume": self.historical_session_volume,
        }
