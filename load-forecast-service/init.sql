-- ============================================================
-- forecast_db — database-skema
-- Load Forecast Bounded Context
-- ============================================================

CREATE DATABASE IF NOT EXISTS forecast_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE forecast_db;

-- ------------------------------------------------------------
-- Tabel: forecast_results
-- Én række pr. ForecastResult-entitet.
-- ------------------------------------------------------------
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
