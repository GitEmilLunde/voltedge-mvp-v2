-- ============================================================
-- charging_session_db — database-skema
-- Charging Session Bounded Context
-- ============================================================

CREATE DATABASE IF NOT EXISTS charging_session_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE charging_session_db;

-- ------------------------------------------------------------
-- Tabel: charging_sessions
-- Én række pr. ChargingSession-aggregat.
-- ------------------------------------------------------------
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
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (session_id),
    INDEX idx_user_id    (user_id),
    INDEX idx_charger_id (charger_id),
    INDEX idx_status     (status),
    INDEX idx_price_area (price_area),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- Tabel: session_events
-- Audit trail for Event-entiteter på sessionen.
-- event_id og session_id er database-tekniske nøgler — ikke domæne-felter.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS session_events (
    event_id    VARCHAR(36)     NOT NULL,
    session_id  VARCHAR(36)     NOT NULL,
    event_type  VARCHAR(30)     NOT NULL COMMENT 'SESSION_AUTHORIZED | SESSION_STARTED | CHARGING_STOPPED | UNEXPECTED_STOPPAGE',
    event_time  DATETIME        NOT NULL,

    PRIMARY KEY (event_id),
    INDEX idx_session_id (session_id),
    INDEX idx_event_time (event_time),
    CONSTRAINT fk_event_session
        FOREIGN KEY (session_id)
        REFERENCES charging_sessions (session_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
