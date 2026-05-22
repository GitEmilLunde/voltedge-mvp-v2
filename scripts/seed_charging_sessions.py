#!/usr/bin/env python3
"""
VoltEdge — Seed script

Dette script gør tre ting:
  1. Henter rigtige danske elspotpriser fra Energidataservice (gratis API fra Energinet)
  2. Genererer realistiske ladesessioner med de rigtige priser
  3. Indsætter sessionerne i databasen

Kør det sådan her:
  python seed_charging_sessions.py
  python seed_charging_sessions.py --sessions 5000
"""

import random
import uuid
from datetime import datetime, timedelta

import requests
import pymysql


# ===========================================================
# TRIN 1 — HENT RIGTIGE SPOTPRISER FRA ENERGIDATASERVICE
# ===========================================================
#
# Energidataservice er Energinets gratis API.
# Vi henter day-ahead elspotpriser for Danmark (DK1 og DK2).
#
# Sådan virker API-kaldet:
#   Vi sender en GET-forespørgsel til en URL med nogle filtre,
#   og API'et svarer med en liste af priser — én pris per time.
#
# Hvert svar-element ser sådan ud:
#   {
#     "TimeDK":      "2026-03-10T08:00:00",  ← hvilken time prisen gælder
#     "PriceArea":   "DK1",                  ← dansk priszone (vest eller øst)
#     "SpotPriceDKK": 720.5                  ← pris i DKK per MWh (ikke kWh!)
#   }
#
# Vi dividerer SpotPriceDKK med 1000 for at omregne til DKK/kWh:
#   720.5 / 1000 = 0.7205 DKK/kWh
#
# Vi henter de seneste 8000 priser (dækker ~5 måneder for DK1+DK2 tilsammen).

def hent_spotpriser():
    print("Henter spotpriser fra Energidataservice...")

    url = "https://api.energidataservice.dk/dataset/Elspotprices"

    svar = requests.get(url, params={
        "filter": '{"PriceArea":["DK1","DK2"]}',
        "sort":   "HourDK desc",
        "limit":  8000,
        "offset": 0,
    }, timeout=30)

    svar.raise_for_status()  # stopper scriptet hvis API-kaldet fejler

    # Byg en opslagstabel: (time, priszone) → pris i DKK/kWh
    # Eksempel: (datetime(2025,6,10,8,0), "DK1") → 0.7205
    # OBS: API'et bruger feltet "HourDK" (ikke "TimeDK")
    priser = {}
    for record in svar.json().get("records", []):
        tidspunkt  = datetime.fromisoformat(record["HourDK"]).replace(minute=0, second=0, microsecond=0)
        priszone   = record["PriceArea"]
        pris_kwh   = round(record["SpotPriceDKK"] / 1000.0, 4)
        priser[(tidspunkt, priszone)] = pris_kwh

    print(f"  Hentet {len(priser)} spotpris-records")
    return priser


def find_spotpris(priser, priszone, tidspunkt):
    # Slår prisen op for den givne time.
    # Returnerer 0.50 DKK/kWh som nødløsning hvis timen ikke findes.
    nøgle = (tidspunkt.replace(minute=0, second=0, microsecond=0), priszone)
    return priser.get(nøgle, 0.50)


# ===========================================================
# TRIN 2 — GENERER REALISTISKE LADESESSIONER
# ===========================================================
#
# Vi har 5 ladestandere fordelt på to priszoner.
# Sessionerne fordeles over de seneste 5 måneder (2026-data).
#
# Vi efterligner reelle mønstre:
#   - Flere sessioner i spidstid (morgen og eftermiddag)
#   - Færre sessioner i weekenden
#   - Lange sessioner i spidstid kan give idle fee
#   - ~4% af sessionerne er fejlbehæftede (FAULTED)

LADESTANDERE = [
    {"charger_id": "CHR-FLEET-001", "connector_id": "CON-A", "price_area": "DK1"},
    {"charger_id": "CHR-FLEET-002", "connector_id": "CON-B", "price_area": "DK1"},
    {"charger_id": "CHR-PRIV-001",  "connector_id": "CON-C", "price_area": "DK2"},
    {"charger_id": "CHR-PRIV-002",  "connector_id": "CON-D", "price_area": "DK2"},
    {"charger_id": "CHR-TAXI-001",  "connector_id": "CON-E", "price_area": "DK1"},
]

KONTRAKTER = {
    "CHR-FLEET-001": [f"FLEET-{i:03d}" for i in range(1, 6)],
    "CHR-FLEET-002": [f"FLEET-{i:03d}" for i in range(1, 6)],
    "CHR-PRIV-001":  [f"PRIV-{i:03d}"  for i in range(1, 11)],
    "CHR-PRIV-002":  [f"PRIV-{i:03d}"  for i in range(1, 11)],
    "CHR-TAXI-001":  [f"TAXI-{i:03d}"  for i in range(1, 4)],
}

# Sandsynlighed for at en session starter i denne time (høj = flere sessioner)
STARTSANDSYNLIGHED_PER_TIME = [
    0.5, 0.3, 0.2, 0.2, 0.3,   # 00–04  (nat)
    0.6, 1.5, 3.5, 3.5, 2.5,   # 05–09  (morgen-spidstid)
    2.0, 1.8, 1.8, 1.8, 2.0,   # 10–14  (dagtimer)
    2.5, 3.0, 4.0, 3.5, 2.5,   # 15–19  (eftermiddags-spidstid)
    2.0, 1.5, 1.0, 0.7,         # 20–23  (aften)
]


def beregn_idle_fee(session_start, session_end):
    # Idle fee opkræves hvis:
    #   - Sessionen startede i spidstid (08:00–20:00)
    #   - OG varede mere end 180 min (grace) + 10 min (buffer) = 190 min
    varighed_min = (session_end - session_start).total_seconds() / 60
    er_spidstid  = 8 <= session_start.hour < 20
    idle_min     = varighed_min - 180 - 10

    if er_spidstid and idle_min > 0:
        return round(idle_min * 1.50, 2)  # 1,50 DKK/min
    return 0.0


def generer_sessioner(antal, maaneder_tilbage, priser):
    # Brug datointervallet fra de faktisk hentede spotpriser
    # så alle sessioner får en reel pris og ikke en fallback
    datoer     = [ts for (ts, _) in priser.keys()]
    start_dato = min(datoer)
    slut_dato  = max(datoer)
    dage_i_alt = (slut_dato - start_dato).days
    print(f"  Genererer sessioner i perioden: {start_dato:%Y-%m-%d} → {slut_dato:%Y-%m-%d}")

    # Målerstand per lader — starter på et realistisk niveau og stiger session for session
    maalerstande = {l["charger_id"]: random.uniform(8_000, 40_000) for l in LADESTANDERE}

    sessioner = []
    random.seed(42)  # samme seed = samme data hver gang scriptet køres

    for _ in range(int(antal * 1.3)):   # generer lidt ekstra og stop når vi har nok
        if len(sessioner) >= antal:
            break

        lader = random.choice(LADESTANDERE)
        cid   = lader["charger_id"]
        dato  = start_dato + timedelta(days=random.randint(0, dage_i_alt))

        # Weekender har færre sessioner
        if dato.weekday() >= 5 and random.random() < 0.40:
            continue

        # Vælg starttidspunkt baseret på hvornår folk typisk lader
        time         = random.choices(range(24), weights=STARTSANDSYNLIGHED_PER_TIME, k=1)[0]
        session_start = dato.replace(hour=time, minute=random.randint(0, 59), second=0)

        if session_start >= slut_dato:
            continue

        # Sessionsvarighed — taxa lader hurtigt, private lader længere
        if "TAXI" in cid:
            varighed = random.randint(25, 90)
        elif time in range(7, 10):      # morgen-rush
            varighed = random.randint(40, 150)
        elif time in range(16, 20):     # eftermiddags-spidstid
            varighed = random.randint(90, 380)  # nogle ender med idle fee
        else:
            varighed = random.randint(60, 300)

        session_end = min(session_start + timedelta(minutes=varighed), slut_dato)

        # ~4% af sessionerne fejler
        er_fejl     = random.random() < 0.04
        status      = "FAULTED" if er_fejl else "COMPLETED"
        stop_reason = "Fault" if er_fejl else random.choices(
            ["Normal", "Timeout", "Administrative"], weights=[90, 7, 3], k=1
        )[0]

        # Reel spotpris fra Energidataservice
        spotpris = find_spotpris(priser, lader["price_area"], session_start)

        # Energi leveret (normal lader ~7 kW — fejlede sessioner leverer næsten intet)
        maaler_start = round(maalerstande[cid], 3)
        energi       = round(random.uniform(0, 1.5), 3) if er_fejl else round(random.uniform(6.0, 8.5) * (varighed / 60), 3)
        maaler_slut  = round(maaler_start + energi, 3)
        maalerstande[cid] = maaler_slut

        idle_fee     = 0.0 if er_fejl else beregn_idle_fee(session_start, session_end)
        session_cost = round(energi * spotpris + idle_fee, 4) if not er_fejl else 0.0

        sessioner.append({
            "session_id":         str(uuid.uuid4()),
            "charger_id":         cid,
            "connector_id":       lader["connector_id"],
            "contract_id":        random.choice(KONTRAKTER[cid]),
            "price_area":         lader["price_area"],
            "status":             status,
            "session_start_time": session_start,
            "session_end_time":   session_end,
            "meter_start":        maaler_start,
            "meter_end":          maaler_slut,
            "energy_delivered":   energi,
            "spot_price_dkk":     spotpris,
            "idle_fee":           idle_fee,
            "session_cost":       session_cost,
            "stop_reason":        stop_reason,
            "created_at":         session_start,
        })

    # Sorter kronologisk så data er klar til time-series analyse
    sessioner.sort(key=lambda s: s["session_start_time"])
    return sessioner


# ===========================================================
# TRIN 3 — INDSÆT I DATABASEN
# ===========================================================

def indsaet_i_database(sessioner, host, port, user, password, db):
    forbindelse = pymysql.connect(
        host=host, port=port, user=user,
        password=password, database=db, charset="utf8mb4",
    )

    sql = """
        INSERT INTO charging_sessions (
            session_id, charger_id, connector_id, contract_id,
            price_area, status, session_start_time, session_end_time,
            meter_start, meter_end, energy_delivered, spot_price_dkk,
            idle_fee, session_cost, stop_reason, created_at
        ) VALUES (
            %(session_id)s, %(charger_id)s, %(connector_id)s, %(contract_id)s,
            %(price_area)s, %(status)s, %(session_start_time)s, %(session_end_time)s,
            %(meter_start)s, %(meter_end)s, %(energy_delivered)s, %(spot_price_dkk)s,
            %(idle_fee)s, %(session_cost)s, %(stop_reason)s, %(created_at)s
        )
    """

    with forbindelse:
        with forbindelse.cursor() as cursor:
            # Indsæt 500 rækker ad gangen (hurtigere end én ad gangen)
            batch_størrelse = 500
            for i in range(0, len(sessioner), batch_størrelse):
                batch = sessioner[i : i + batch_størrelse]
                cursor.executemany(sql, batch)
                forbindelse.commit()
                print(f"  → {min(i + batch_størrelse, len(sessioner)):>5} / {len(sessioner)} rækker indsat")


# ===========================================================
# KØR SCRIPTET
# ===========================================================

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=2000,   help="Antal sessioner (default: 2000)")
    parser.add_argument("--months",   type=int, default=5,      help="Måneder tilbage (default: 5 = 2026 til dato)")
    parser.add_argument("--host",     default="localhost")
    parser.add_argument("--port",     type=int, default=3308)
    parser.add_argument("--user",     default="voltedge")
    parser.add_argument("--password", default="voltedge_secret")
    parser.add_argument("--db",       default="charging_session_db")
    args = parser.parse_args()

    print("\nVoltEdge — Data Seed")
    print("=" * 40)

    # Trin 1: Hent rigtige spotpriser
    priser = hent_spotpriser()

    # Trin 2: Generer sessioner med de rigtige priser
    print(f"\nGenererer {args.sessions} sessioner...")
    sessioner = generer_sessioner(args.sessions, args.months, priser)

    # Vis hvad vi har genereret
    completed = [s for s in sessioner if s["status"] == "COMPLETED"]
    faulted   = [s for s in sessioner if s["status"] == "FAULTED"]
    med_idle  = [s for s in sessioner if s["idle_fee"] > 0]
    print(f"  COMPLETED    : {len(completed)}")
    print(f"  FAULTED      : {len(faulted)}  ({100*len(faulted)/len(sessioner):.1f}%)")
    print(f"  Med idle fee : {len(med_idle)}")
    if completed:
        print(f"  Total energi : {sum(s['energy_delivered'] for s in completed):.0f} kWh")
        print(f"  Total omsætn.: {sum(s['session_cost'] for s in completed):.0f} DKK")
    print(f"  Periode      : {sessioner[0]['session_start_time']:%Y-%m-%d} → {sessioner[-1]['session_start_time']:%Y-%m-%d}")

    # Trin 3: Indsæt i database
    print(f"\nForbinder til {args.host}:{args.port}/{args.db}...")
    indsaet_i_database(sessioner, args.host, args.port, args.user, args.password, args.db)
    print(f"\nFærdig — {len(sessioner)} sessioner indsat.\n")


if __name__ == "__main__":
    main()
