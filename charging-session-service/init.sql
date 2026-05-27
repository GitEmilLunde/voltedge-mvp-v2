-- ============================================================
-- VoltEdge MVP — kombineret database-skema
-- Begge bounded contexts i ét MySQL-instance
-- ============================================================

-- ------------------------------------------------------------
-- Charging Session Bounded Context
-- ------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS charging_session_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE charging_session_db;

CREATE TABLE IF NOT EXISTS charging_sessions (
    session_id          VARCHAR(36)     NOT NULL,
    user_id             VARCHAR(36)     NOT NULL,
    charger_id          VARCHAR(50)     NOT NULL,
    charger_type        VARCHAR(20)     NOT NULL COMMENT 'Normal Charger | Fast Charger',
    price_area          VARCHAR(5)      NOT NULL COMMENT 'DK1 | DK2',
    status              VARCHAR(15)     NOT NULL COMMENT 'AFVENTER | AUTORISERET | AKTIV | AFSLUTTET | FEJLET',
    applied_spot_price  DECIMAL(10, 6)  NULL     COMMENT 'DKK/kWh — låst ved SESSION_AUTHORIZED',
    start_time          DATETIME        NULL,
    end_time            DATETIME        NULL,
    energy_delivered    DECIMAL(10, 4)  NULL     COMMENT 'kWh — aldrig negativ',
    session_cost        DECIMAL(12, 4)  NULL     COMMENT 'DKK = EnergyDelivered × AppliedSpotPrice',
    charging_status     VARCHAR(15)     NULL     COMMENT 'UNBOTHERED | BOTHERED — sat ved AFSLUTTET eller FEJLET',
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (session_id),
    INDEX idx_user_id         (user_id),
    INDEX idx_charger_id      (charger_id),
    INDEX idx_status          (status),
    INDEX idx_price_area      (price_area),
    INDEX idx_charging_status (charging_status),
    INDEX idx_created_at      (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS session_events (
    event_id    VARCHAR(36)     NOT NULL,
    session_id  VARCHAR(36)     NOT NULL,
    error_type  VARCHAR(20)     NULL     COMMENT 'POWER_LOSS | CONNECTOR_FAULT | NETWORK_ERROR | OVERHEATING | UNKNOWN — NULL hvis ingen fejl',
    event_time  DATETIME        NOT NULL,

    PRIMARY KEY (event_id),
    INDEX idx_session_id (session_id),
    INDEX idx_event_time (event_time),
    CONSTRAINT fk_event_session
        FOREIGN KEY (session_id)
        REFERENCES charging_sessions (session_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Giv voltedge-brugeren adgang til begge databaser
GRANT ALL PRIVILEGES ON charging_session_db.* TO 'voltedge'@'%';
GRANT ALL PRIVILEGES ON forecast_db.*          TO 'voltedge'@'%';
FLUSH PRIVILEGES;

-- ------------------------------------------------------------
-- Load Forecast Bounded Context
-- ------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS forecast_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE forecast_db;

CREATE TABLE IF NOT EXISTS forecast_results (
    forecast_id         VARCHAR(36)     NOT NULL,
    model_id            VARCHAR(36)     NOT NULL,
    hour_of_day         TINYINT         NOT NULL COMMENT '0–23',
    day_of_week         TINYINT         NOT NULL COMMENT '1–7 (1 = mandag)',
    spot_price          DECIMAL(10, 6)  NOT NULL COMMENT 'DKK/kWh',
    session_count       INT             NOT NULL COMMENT 'Historisk antal sessions ≥ 0',
    predicted_count     DECIMAL(10, 2)  NOT NULL COMMENT 'Forudsagt antal sessions ≥ 0',
    forecast_timestamp  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (forecast_id),
    INDEX idx_model_id           (model_id),
    INDEX idx_forecast_timestamp (forecast_timestamp),
    INDEX idx_hour_dow           (hour_of_day, day_of_week)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
