import logging
from flask import Flask
from .extensions import db


def create_app(config=None):
    app = Flask(__name__)

    if config:
        app.config.from_object(config)
    else:
        from config import Config
        app.config.from_object(Config)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    db.init_app(app)

    with app.app_context():
        from .domain.aggregates.charging_session import ChargingSession  # noqa: F401
        db.create_all()

        from .infrastructure.external.spot_price_client import SpotPriceClient
        app.extensions["spot_price_client"] = SpotPriceClient(
            app.config.get("ENERGIDATASERVICE_URL", "")
        )

        from .presentation.routes import sessions_bp
        app.register_blueprint(sessions_bp)

    return app
