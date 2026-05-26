"""
Konfiguration — charging-session-service.

Alle miljøvariabler læses her. Infrastrukturlaget bruger Config-objektet
direkte — ingen hardcodede værdier andre steder.
"""

import os


class Config:
    """Applikationskonfiguration læst fra miljøvariabler."""

    # MySQL
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "voltedge")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "voltedge_pass")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "charging_session_db")

    # SpotPriceClient
    SPOT_PRICE_TIMEOUT_SEC: int = int(os.getenv("SPOT_PRICE_TIMEOUT_SEC", "5"))

    # Flask
    DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    PORT: int = int(os.getenv("PORT", "5001"))

    @classmethod
    def database_url(cls) -> str:
        """Returnerer SQLAlchemy database-URL."""
        return (
            f"mysql+pymysql://{cls.MYSQL_USER}:{cls.MYSQL_PASSWORD}"
            f"@{cls.MYSQL_HOST}:{cls.MYSQL_PORT}/{cls.MYSQL_DATABASE}"
            "?charset=utf8mb4"
        )
