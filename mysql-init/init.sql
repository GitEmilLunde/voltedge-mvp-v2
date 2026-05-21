-- VoltEdge MVP — Initialiser begge databaser ved opstart
CREATE DATABASE IF NOT EXISTS charging_session_db;
CREATE DATABASE IF NOT EXISTS forecast_db;

GRANT ALL PRIVILEGES ON charging_session_db.* TO 'voltedge'@'%';
GRANT ALL PRIVILEGES ON forecast_db.* TO 'voltedge'@'%';
FLUSH PRIVILEGES;

-- ──────────────────────────────────────────────
-- Charging Session Database
-- ──────────────────────────────────────────────
USE charging_session_db;

CREATE TABLE IF NOT EXISTS charging_sessions (
    session_id         VARCHAR(36)  PRIMARY KEY,
    charger_id         VARCHAR(50)  NOT NULL,
    connector_id       VARCHAR(50)  NOT NULL,
    contract_id        VARCHAR(50)  NOT NULL,
    charger_type       ENUM('fast','normal') NOT NULL,
    price_area         ENUM('DK1','DK2') NOT NULL,
    status             ENUM('PENDING','AUTHORIZED','ACTIVE','COMPLETED','FAULTED') DEFAULT 'PENDING',
    session_start_time DATETIME,
    session_end_time   DATETIME,
    meter_start        FLOAT,
    meter_end          FLOAT,
    energy_delivered   FLOAT,        -- beregnet: meter_end - meter_start
    spot_price_dkk     FLOAT,        -- låst ved sessionstart fra Energidataservice
    idle_fee           FLOAT,        -- 10 DKK hvis session > 3t i 08:00-20:00
    session_cost       FLOAT,        -- energy_delivered × spot_price_dkk + idle_fee
    stop_reason        ENUM('Normal','Timeout','Fault','Administrative'),
    created_at         DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ──────────────────────────────────────────────
-- Forecast Database
-- ──────────────────────────────────────────────
USE forecast_db;

CREATE TABLE IF NOT EXISTS forecast_results (
    forecast_id                VARCHAR(36) PRIMARY KEY,
    charger_id                 VARCHAR(50) NOT NULL,
    generated_at               DATETIME DEFAULT CURRENT_TIMESTAMP,
    prediction_window_hours    INT DEFAULT 24,
    load_index                 FLOAT,
    temperature                FLOAT,
    wind_speed                 FLOAT,
    spot_price_forecast        FLOAT,
    historical_session_volume  INT
);
