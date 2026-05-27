"""
Seed-script — genererer 2000 realistiske ChargingSession-records.

Fordeler sessions over:
  - 25 ladere (12 Normal Charger, 13 Fast Charger)
    → Skæv fordeling: 3–4 hotspot-ladere tager langt størstedelen af trafikken
  - 100 brugere — jævnt fordelt, ingen aktivitetsniveauer
  - Begge priszoner (DK1 og DK2)
  - De seneste 180 dage (6 måneder)
  - Realistisk dagsmønster (flest sessions morgen og eftermiddag)
  - Alle 5 tilstande repræsenteret (AFVENTER, AUTORISERET, AKTIV, AFSLUTTET, FEJLET)

Kører direkte mod MySQL via charging_session_db.
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

# 25 ladere med popularitetsvægte
# (id, type, vægt) — høj vægt = travl lader
LADERE_MED_VÆGTE = [
    # Normal Charger — 12 stk
    ("charger-001", "Normal Charger", 14),   # travleste Normal Charger
    ("charger-002", "Normal Charger", 11),
    ("charger-003", "Normal Charger",  9),
    ("charger-004", "Normal Charger",  7),
    ("charger-005", "Normal Charger",  5),
    ("charger-006", "Normal Charger",  4),
    ("charger-007", "Normal Charger",  3),
    ("charger-008", "Normal Charger",  2),
    ("charger-009", "Normal Charger",  2),
    ("charger-010", "Normal Charger",  1),
    ("charger-011", "Normal Charger",  1),
    ("charger-012", "Normal Charger",  1),
    # Fast Charger — 13 stk
    ("charger-013", "Fast Charger",   20),   # absolut travleste lader
    ("charger-014", "Fast Charger",   16),
    ("charger-015", "Fast Charger",   13),
    ("charger-016", "Fast Charger",   10),
    ("charger-017", "Fast Charger",    7),
    ("charger-018", "Fast Charger",    5),
    ("charger-019", "Fast Charger",    4),
    ("charger-020", "Fast Charger",    3),
    ("charger-021", "Fast Charger",    2),
    ("charger-022", "Fast Charger",    2),
    ("charger-023", "Fast Charger",    1),
    ("charger-024", "Fast Charger",    1),
    ("charger-025", "Fast Charger",    1),
]

LADERE_IDS  = [(cid, ctype) for cid, ctype, _ in LADERE_MED_VÆGTE]
LADER_VÆGTE = [vægt for _, _, vægt in LADERE_MED_VÆGTE]

# 100 brugere — jævnt fordelt
BRUGERE = [f"user-{i:03d}" for i in range(1, 101)]

PRISZONER = ["DK1", "DK2"]

# Spotpriser i DKK/kWh — realistisk dansk interval
SPOTPRISER = {
    "DK1": [0.45, 0.62, 0.78, 0.95, 1.10, 1.25, 1.42, 1.58, 1.75, 1.90, 2.10, 2.35, 2.65, 3.10],
    "DK2": [0.50, 0.68, 0.82, 1.00, 1.15, 1.30, 1.48, 1.62, 1.80, 1.95, 2.15, 2.40, 2.70, 3.20],
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
    t = random.choices(TIMER, weights=TIDSVÆGTE, k=1)[0]
    minutter = random.randint(0, 59)
    return base_dato.replace(hour=t, minute=minutter, second=0, microsecond=0, tzinfo=timezone.utc)


def generer_sessions(antal: int = 2000):
    """Genererer liste af session-dicts klar til INSERT."""
    sessions = []
    nu = datetime.now(timezone.utc)

    for _ in range(antal):
        session_id = str(uuid4())

        # Jævnt fordelte brugere
        user_id = random.choice(BRUGERE)

        # Skæv lader-fordeling — populære ladere får langt mere trafik
        charger_id, charger_type = random.choices(LADERE_IDS, weights=LADER_VÆGTE, k=1)[0]

        price_area = random.choice(PRISZONER)
        spot_price = random.choice(SPOTPRISER[price_area])

        # Tidspunkt spredt over de seneste 180 dage (6 måneder)
        dage_tilbage = random.randint(0, 180)
        base = nu - timedelta(days=dage_tilbage)
        oprettet = vælg_tidspunkt(base)

        # Kun afsluttede sessioner i DB — ~93% AFSLUTTET, ~7% FEJLET
        fejlet = random.random() < 0.07

        start_time = oprettet + timedelta(minutes=2)

        if not fejlet:
            if charger_type == "Normal Charger":
                minutter = random.randint(20, 90)
                energy_delivered = round(random.uniform(4.0, 22.0), 2)
            else:
                minutter = random.randint(10, 40)
                energy_delivered = round(random.uniform(15.0, 60.0), 2)

            end_time        = start_time + timedelta(minutes=minutter)
            session_cost    = round(energy_delivered * spot_price, 4)
            charging_status = "UNBOTHERED"
            events          = []  # ingen events — kun BOTHERED gemmer events
        else:
            end_time         = start_time + timedelta(minutes=random.randint(3, 25))
            energy_delivered = None
            session_cost     = None
            charging_status  = "BOTHERED"
            fejl_typer = ["POWER_LOSS", "CONNECTOR_FAULT", "NETWORK_ERROR", "OVERHEATING", "UNKNOWN"]
            events = [(random.choice(fejl_typer), end_time)]

        sessions.append({
            "session_id":         session_id,
            "user_id":            user_id,
            "charger_id":         charger_id,
            "charger_type":       charger_type,
            "price_area":         price_area,
            "applied_spot_price": spot_price,
            "start_time":         start_time,
            "end_time":           end_time,
            "energy_delivered":   energy_delivered,
            "session_cost":       session_cost,
            "charging_status":    charging_status,
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
                         applied_spot_price, start_time, end_time,
                         energy_delivered, session_cost, charging_status)
                    VALUES
                        (:session_id, :user_id, :charger_id, :charger_type, :price_area,
                         :applied_spot_price, :start_time, :end_time,
                         :energy_delivered, :session_cost, :charging_status)
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
