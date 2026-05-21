import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


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
        from .models import ForecastResult  # noqa: F401
        db.create_all()

        from .routes import forecast_bp
        app.register_blueprint(forecast_bp)

    return app
