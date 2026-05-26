"""
Indgangspunkt — charging-session-service.

Initialiserer database-forbindelse, repositories, services og Flask-app.
Dependency Injection sker her — ikke i domain- eller application-laget.
"""

import logging
import time

from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.application.session_application_service import SessionApplicationService
from app.config import Config
from app.infrastructure.external.spot_price_client import SpotPriceClient
from app.infrastructure.repositories.session_repository import SessionRepository
from app.presentation.routes import create_blueprint

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def _vent_paa_database(engine, max_forsøg: int = 10, pause_sek: float = 3.0) -> None:
    """Venter til MySQL er klar — bruges ved Docker Compose opstart."""
    for forsøg in range(1, max_forsøg + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database forbundet.")
            return
        except OperationalError:
            logger.warning("Venter på database (%d/%d)...", forsøg, max_forsøg)
            time.sleep(pause_sek)
    raise RuntimeError("Kunne ikke oprette forbindelse til databasen efter %d forsøg" % max_forsøg)


def create_app() -> Flask:
    """Factory-funktion der opretter og konfigurerer Flask-applikationen."""
    app = Flask(__name__)

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    engine = create_engine(
        Config.database_url(),
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    _vent_paa_database(engine)

    # ------------------------------------------------------------------
    # Dependency Injection
    # ------------------------------------------------------------------
    repository = SessionRepository(engine=engine)
    spot_price_client = SpotPriceClient(
        timeout_sekunder=Config.SPOT_PRICE_TIMEOUT_SEC
    )
    service = SessionApplicationService(
        repository=repository,
        spot_price_client=spot_price_client,
    )

    # ------------------------------------------------------------------
    # Blueprint
    # ------------------------------------------------------------------
    bp = create_blueprint(service)
    app.register_blueprint(bp)

    logger.info("charging-session-service klar på port %d", Config.PORT)
    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
