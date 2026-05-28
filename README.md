# VoltEdge MVP

**Example on Charging Infrastructure builded from Events Storming & Domain-Driven Design**

VoltEdge MVP demonstrerer en datadrevet platform til styring og dokumentation af EV-ladesessioner bygget på Domain-Driven Design. Systemet består af to mikroservices der realiserer to bounded contexts: Charging Session Management (core) og Energy Price Integration (supporting). Den data systemet producerer danner grundlag for ekstern analyse og load forecasting i Jupyter Notebook.

---

## Kom i gang

### Krav

Sørg for at følgende er installeret:

- [Docker Desktop](https://www.docker.com/products/docker-desktop)
- [Git](https://git-scm.com)

### Start systemet

```bash
git clone https://github.com/GitEmilLunde/voltedge-mvp-v2.git
cd voltedge-mvp-v2
docker compose up --build
```

Dette starter automatisk MySQL, begge services og et seed-script der indsætter 2000 realistiske ladesessioner. Første gang tager det 2-3 minutter.

Systemet er klar når du ser:

```
voltedge-charging-session  | charging-session-service klar på port 5001
voltedge-load-forecast     | load-forecast-service klar på port 5002
voltedge-seed              | ✅ 2000 sessions seedet succesfuldt.
```

Tjek at begge services kører:

```bash
curl http://localhost:5001/health
curl http://localhost:5002/health
```

Stop systemet:

```bash
docker compose down        # bevar data
docker compose down -v     # slet data og start forfra
```

---

## API

### Charging Session Service — Port 5001

En session følger denne tilstandsmaskine: `AFVENTER → AUTORISERET → AKTIV → AFSLUTTET | FEJLET`

```bash
# Opret session
POST /sessions
{
  "user_id": "user-001",
  "charger_id": "charger-013",
  "charger_type": "Fast Charger",
  "price_area": "DK1"
}

# Autoriser — låser spotpris fra Energidataservice
POST /sessions/{session_id}/autoriser

# Start opladning — kWh-tælling begynder
POST /sessions/{session_id}/start

# Stop opladning — beregner SessionCost
POST /sessions/{session_id}/stop
{ "energy_delivered_kwh": 24.5 }

# Registrer fejl
POST /sessions/{session_id}/fejl

# Hent session / alle sessioner
GET /sessions/{session_id}
GET /sessions
```

### Load Forecast Service — Port 5002

```bash
# Træn ForecastModel på historiske sessionsdata
POST /forecast/train

# Generer ForecastResult
POST /forecast/predict
{
  "hour_of_day": 17,
  "day_of_week": 3,
  "spot_price": 1.25
}

# Hent alle prognoser
GET /forecast/results
```

---

## DDD-domænemodel

Koden er organiseret efter DDD-lagene. Her er en hurtig guide til hvor du finder aggregater, entiteter og value objects.

### Charging Session Bounded Context

```
charging-session-service/app/domain/
├── aggregates/
│   └── charging_session.py     ← Aggregate: ChargingSession
│                                  Aggregate Root ID: ChargingSessionID
│                                  Entity: Event
├── value_objects/
│   └── value_objects.py        ← UserID, StartTime, EndTime,
│                                  EnergyDelivered, AppliedSpotPrice,
│                                  SessionCost, ChargerType,
│                                  EventType, EventTime,
│                                  ChargingStatus
```

De vigtigste regler der håndhæves i `charging_session.py`:

- `AppliedSpotPrice` låses ved `autoriser()` og må aldrig overskrives
- `SessionCost` beregnes kun ved `stop_opladning()` som `EnergyDelivered × AppliedSpotPrice`
- `EnergyDelivered` er aldrig negativ
- Tilstandsovergange sker kun via `SessionLifecycle`

### Energy Price Integration Bounded Context

```
charging-session-service/app/infrastructure/external/
└── spot_price_client.py        ← Aggregate Root: SpotPriceRecord
                                   Value Objects: PriceArea (DK1|DK2),
                                   CalculatedSpotPrice
```

Spotprisen hentes fra [Energidataservice DayAheadPrices API](https://api.energidataservice.dk/dataset/DayAheadPrices?limit=5) — offentligt tilgængeligt, kræver ingen nøgle. Ved netværksfejl anvendes en fallback-pris.

### Load Forecasting Bounded Context

```
load-forecast-service/app/domain/
├── aggregates/
│   └── forecast_model.py       ← Aggregate Root: ForecastModel
│                                  Entity: ForecastResult
├── value_objects/
│   └── value_objects.py        ← TimeFeature (hour_of_day, day_of_week)
│                                  PriceFeatures (spot_price)
│                                  SessionCount (historisk antal sessioner)
```

`ForecastModel` trænes med `RandomForestRegressor` på `TimeFeature`, `PriceFeatures` og `SessionCount` og returnerer et `ForecastResult` med `predicted_count`.

---

## Database og SQL Workbench

Systemet bruger MySQL på port `3308` med to databaser. Brugernavn og adgangskode findes i `docker-compose.yml` under environment-variablerne `MYSQL_USER` og `MYSQL_PASSWORD`.

Forbind i MySQL Workbench:

```
Hostname:  127.0.0.1
Port:      3308
Username:  Se MYSQL_USER i docker-compose.yml
Password:  Se MYSQL_PASSWORD i docker-compose.yml
```

Nyttige forespørgsler:

```sql
-- Alle afsluttede sessioner
SELECT * FROM charging_session_db.charging_sessions
WHERE charging_status = 'UNBOTHERED'
ORDER BY end_time DESC;

-- Fejlede sessioner med fejltype
SELECT s.session_id, s.charger_id, s.charger_type, e.error_type
FROM charging_session_db.charging_sessions s
JOIN charging_session_db.session_events e ON s.session_id = e.session_id
WHERE s.charging_status = 'BOTHERED';

-- Belastning per time på dagen
SELECT HOUR(start_time) AS time, COUNT(*) AS antal
FROM charging_session_db.charging_sessions
GROUP BY HOUR(start_time)
ORDER BY time;
```

---

## Tests og CI/CD

```bash
# Kør tests lokalt
cd charging-session-service && pytest tests/ -v
cd load-forecast-service    && pytest tests/ -v
```

GitHub Actions kører automatisk ved push til `main`:

1. Tests for begge services
2. Byg og push Docker images til GitHub Container Registry (kun hvis alle tests er grønne)

---

## Tech Stack

| | |
|---|---|
| Sprog | Python 3.11 |
| API | Flask 3.0 |
| Database | MySQL 8.0 via SQLAlchemy |
| ML | scikit-learn RandomForestRegressor |
| Container | Docker + Docker Compose |
| CI/CD | GitHub Actions |
| Ekstern datakilde | [Energidataservice DayAheadPrices](https://www.energidataservice.dk/tso-electricity/DayAheadPrices) |
