"""
Indgangspunkt — load-forecast-service.

Initialiserer database, repositories, services og Flask-app.
"""

import logging
import time

from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.application.forecast_application_service import ForecastApplicationService
from app.config import Config
from app.infrastructure.external.session_data_client import SessionDataClient
from app.infrastructure.repositories.forecast_repository import ForecastRepository
from app.presentation.routes import create_blueprint

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def _vent_paa_database(engine, max_forsøg: int = 10, pause_sek: float = 3.0) -> None:
    for forsøg in range(1, max_forsøg + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database forbundet.")
            return
        except OperationalError:
            logger.warning("Venter på database (%d/%d)...", forsøg, max_forsøg)
            time.sleep(pause_sek)
    raise RuntimeError("Kunne ikke oprette forbindelse til databasen")


def create_app() -> Flask:
    app = Flask(__name__)

    engine = create_engine(
        Config.database_url(),
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    _vent_paa_database(engine)

    repository = ForecastRepository(engine=engine)
    session_client = SessionDataClient(
        base_url=Config.CHARGING_SESSION_URL,
        timeout_sek=Config.SESSION_DATA_TIMEOUT_SEC,
    )
    service = ForecastApplicationService(
        repository=repository,
        session_data_client=session_client,
    )

    bp = create_blueprint(service)
    app.register_blueprint(bp)

    logger.info("load-forecast-service klar på port %d", Config.PORT)
    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
