"""Konfiguration — load-forecast-service."""

import os


class Config:
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "voltedge")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "voltedge_pass")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "forecast_db")

    CHARGING_SESSION_URL: str = os.getenv(
        "CHARGING_SESSION_URL", "http://charging-session-service:5001"
    )
    SESSION_DATA_TIMEOUT_SEC: int = int(os.getenv("SESSION_DATA_TIMEOUT_SEC", "10"))

    DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    PORT: int = int(os.getenv("PORT", "5002"))

    @classmethod
    def database_url(cls) -> str:
        return (
            f"mysql+pymysql://{cls.MYSQL_USER}:{cls.MYSQL_PASSWORD}"
            f"@{cls.MYSQL_HOST}:{cls.MYSQL_PORT}/{cls.MYSQL_DATABASE}"
            "?charset=utf8mb4"
        )
