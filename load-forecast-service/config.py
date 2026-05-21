import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    MYSQL_HOST     = os.getenv("MYSQL_HOST", "db")
    MYSQL_PORT     = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_USER     = os.getenv("MYSQL_USER", "voltedge")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "voltedge_secret")
    MYSQL_FORECAST_DB = os.getenv("MYSQL_FORECAST_DB", "forecast_db")
    MYSQL_SESSION_DB  = os.getenv("MYSQL_SESSION_DB",  "charging_session_db")

    DMI_API_URL           = os.getenv("DMI_API_URL", "")
    ENERGIDATASERVICE_URL = os.getenv(
        "ENERGIDATASERVICE_URL",
        "https://api.energidataservice.dk/dataset/DayAheadPrices"
    )

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_FORECAST_DB}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Separat URI til kryds-database forespørgsler (historisk session data)
    SESSION_DB_URI = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_SESSION_DB}"
    )
