"""
Seed-script — genererer 2000 realistiske ChargingSession-records.

Fordeler sessions over:
  - 12 ladere (6 Normal Charger, 6 Fast Charger)
  - 40 brugere
  - Begge priszoner (DK1 og DK2)
  - De seneste 180 dage (6 måneder)
  - Realistisk dagsmønster (flest sessions morgen og eftermiddag)
  - Alle 5 tilstande repræsenteret (AFVENTER, AUTORISERET, AKTIV, AFSLUTTET, FEJLET)
  - Sæsonvariation: lavere forbrug sommer, højere vinter

Kører direkte mod MySQL via charging_session_db.
Bruges ved Docker Compose opstart via init.sql eller manuel kørsel.
"""

import random
import sys
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
DB_URL = "mysql+pymysql://voltedge:voltedge_pass@localhost:3306/charging_session_db?charset=utf8mb4"

LADERE = [
    ("charger-001", "Normal Charger"),
    ("charger-002", "Normal Charger"),
    ("charger-003", "Normal Charger"),
    ("charger-004", "Normal Charger"),
    ("charger-005", "Normal Charger"),
    ("charger-006", "Normal Charger"),
    ("charger-007", "Fast Charger"),
    ("charger-008", "Fast Charger"),
    ("charger-009", "Fast Charger"),
    ("charger-010", "Fast Charger"),
    ("charger-011", "Fast Charger"),
    ("charger-012", "Fast Charger"),
]

BRUGERE = [f"user-{i:03d}" for i in range(1, 41)]

PRISZONER = ["DK1", "DK2"]

# Spotpriser i DKK/kWh — realistisk dansk interval
SPOTPRISER = {
    "DK1": [0.45, 0.62, 0.78, 0.95, 1.10, 1.25, 1.42, 1.58, 1.75, 1.90, 2.10, 2.35],
    "DK2": [0.50, 0.68, 0.82, 1.00, 1.15, 1.30, 1.48, 1.62, 1.80, 1.95, 2.15, 2.40],
}

# Vægtet tidsmønster — sandsynlighed pr. time (0–23)
TIDSVÆGTE = [
    0.5, 0.3, 0.2, 0.2, 0.3, 0.8,   # 00–05
    1.5, 2.5, 3.0, 2.8, 2.5, 2.0,   # 06–11
    1.8, 1.5, 1.8, 2.2, 3.0, 3.5,   # 12–17
    3.2, 2.8, 2.2, 1.8, 1.2, 0.8,   # 18–23
]
TIMER = list(range(24))


def vælg_tidspunkt(base_dato: datetime) -> datetime:
    """Vælger et realistisk tidspunkt på base_dato."""
    time = random.choices(TIMER, weights=TIDSVÆGTE, k=1)[0]
    minutter = random.randint(0, 59)
    return base_dato.replace(hour=time, minute=minutter, second=0, microsecond=0, tzinfo=timezone.utc)


def generer_sessions(antal: int = 2000):
    """Genererer liste af session-dicts klar til INSERT."""
    sessions = []
    nu = datetime.now(timezone.utc)

    for i in range(antal):
        session_id = str(uuid4())
        user_id = random.choice(BRUGERE)
        charger_id, charger_type = random.choice(LADERE)
        price_area = random.choice(PRISZONER)
        spot_price = random.choice(SPOTPRISER[price_area])

        # Tidspunkt spredt over de seneste 180 dage (6 måneder)
        dage_tilbage = random.randint(0, 180)
        base = nu - timedelta(days=dage_tilbage)
        oprettet = vælg_tidspunkt(base)

        # Tilstand fordeling: ~70% AFSLUTTET, ~10% AKTIV, ~8% AUTORISERET, ~7% AFVENTER, ~5% FEJLET
        tilstand_vægte = [7, 8, 10, 70, 5]
        tilstand = random.choices(
            ["AFVENTER", "AUTORISERET", "AKTIV", "AFSLUTTET", "FEJLET"],
            weights=tilstand_vægte,
            k=1,
        )[0]

        applied_price = None
        start_time = None
        end_time = None
        energy_delivered = None
        session_cost = None
        events = []

        if tilstand in ("AUTORISERET", "AKTIV", "AFSLUTTET", "FEJLET"):
            applied_price = spot_price
            events.append((None, oprettet + timedelta(minutes=1)))

        if tilstand in ("AKTIV", "AFSLUTTET", "FEJLET"):
            start_time = oprettet + timedelta(minutes=2)
            events.append((None, start_time))

        if tilstand == "AFSLUTTET":
            # Normal: 20–60 min, Fast: 10–30 min
            minutter = random.randint(20, 60) if charger_type == "Normal Charger" else random.randint(10, 30)
            end_time = start_time + timedelta(minutes=minutter)

            # Normal: 5–22 kWh, Fast: 15–50 kWh
            if charger_type == "Normal Charger":
                energy_delivered = round(random.uniform(5.0, 22.0), 2)
            else:
                energy_delivered = round(random.uniform(15.0, 50.0), 2)

            session_cost = round(energy_delivered * applied_price, 4)
            events.append((None, end_time))

        elif tilstand == "FEJLET":
            minutter = random.randint(3, 25)
            end_time = start_time + timedelta(minutes=minutter)
            fejl_typer = ["POWER_LOSS", "CONNECTOR_FAULT", "NETWORK_ERROR", "OVERHEATING", "UNKNOWN"]
            events.append((random.choice(fejl_typer), end_time))

        sessions.append({
            "session_id":         session_id,
            "user_id":            user_id,
            "charger_id":         charger_id,
            "charger_type":       charger_type,
            "price_area":         price_area,
            "status":             tilstand,
            "applied_spot_price": applied_price,
            "start_time":         start_time,
            "end_time":           end_time,
            "energy_delivered":   energy_delivered,
            "session_cost":       session_cost,
            "created_at":         oprettet,
            "charging_status":    "UNBOTHERED" if tilstand == "AFSLUTTET" else ("BOTHERED" if tilstand == "FEJLET" else None),
            "events":             events,
        })

    return sessions


def seed(engine) -> None:
    """Indsætter alle sessions og events i databasen."""
    sessions = generer_sessions(2000)
    print(f"Indsætter {len(sessions)} sessions...")

    with engine.begin() as conn:
        for s in sessions:
            conn.execute(
                text("""
                    INSERT IGNORE INTO charging_sessions
                        (session_id, user_id, charger_id, charger_type, price_area,
                         status, applied_spot_price, start_time, end_time,
                         energy_delivered, session_cost, charging_status, created_at)
                    VALUES
                        (:session_id, :user_id, :charger_id, :charger_type, :price_area,
                         :status, :applied_spot_price, :start_time, :end_time,
                         :energy_delivered, :session_cost, :charging_status, :created_at)
                """),
                {k: v for k, v in s.items() if k != "events"},
            )

            for error_type, event_time in s["events"]:
                conn.execute(
                    text("""
                        INSERT IGNORE INTO session_events
                            (event_id, session_id, error_type, event_time)
                        VALUES
                            (:event_id, :session_id, :error_type, :event_time)
                    """),
                    {
                        "event_id":   str(uuid4()),
                        "session_id": s["session_id"],
                        "error_type": error_type,
                        "event_time": event_time,
                    },
                )

    print(f"✅ {len(sessions)} sessions seedet succesfuldt.")


def vent_paa_db(engine, max_forsøg: int = 15) -> None:
    for i in range(1, max_forsøg + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError:
            print(f"Venter på database ({i}/{max_forsøg})...")
            time.sleep(3)
    print("Kunne ikke forbinde til databasen — afbryder seed.")
    sys.exit(1)


if __name__ == "__main__":
    db_url = sys.argv[1] if len(sys.argv) > 1 else DB_URL
    engine = create_engine(db_url, pool_pre_ping=True)
    vent_paa_db(engine)
    seed(engine)
