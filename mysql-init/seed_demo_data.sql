-- ══════════════════════════════════════════════════════
-- VoltEdge MVP — Demo seed data til MySQL Workbench
-- Kør denne fil direkte i MySQL Workbench mod charging_session_db
-- ══════════════════════════════════════════════════════

USE charging_session_db;

-- Ryd eksisterende testdata
DELETE FROM charging_sessions WHERE charger_id LIKE 'DEMO-%';

-- ──────────────────────────────────────────────
-- 1. Afsluttet normal session — DK1
-- ──────────────────────────────────────────────
INSERT INTO charging_sessions VALUES (
    'demo-sess-001',
    'DEMO-CHR-001', 'CON-A', 'CONTRACT-FLEET-01',
    'DK1', 'COMPLETED',
    '2024-06-10 08:15:00', '2024-06-10 09:45:00',
    12500.0, 12542.5,
    42.5,           -- energy_delivered kWh
    0.6200,         -- spot_price DKK/kWh (morgen-spidstid)
    0.00,           -- ingen idle fee (under 3t)
    26.35,          -- 42.5 × 0.62 = 26.35 DKK
    'Normal',
    NOW()
);

-- ──────────────────────────────────────────────
-- 2. Session MED idle fee — DK2, > 3 timer i spidstid
-- ──────────────────────────────────────────────
INSERT INTO charging_sessions VALUES (
    'demo-sess-002',
    'DEMO-CHR-002', 'CON-B', 'CONTRACT-PRIV-07',
    'DK2', 'COMPLETED',
    '2024-06-10 09:00:00', '2024-06-10 13:30:00',
    8000.0, 8022.0,
    22.0,           -- energy_delivered kWh
    0.5800,         -- spot_price DKK/kWh
    10.00,          -- idle fee: > 3t i spidstid (09:00 start, 4.5t session)
    22.76,          -- 22.0 × 0.58 + 10 = 22.76 DKK
    'Normal',
    NOW()
);

-- ──────────────────────────────────────────────
-- 3. Faulted session
-- ──────────────────────────────────────────────
INSERT INTO charging_sessions VALUES (
    'demo-sess-003',
    'DEMO-CHR-001', 'CON-A', 'CONTRACT-FLEET-01',
    'DK1', 'FAULTED',
    '2024-06-10 11:00:00', '2024-06-10 11:08:00',
    20100.0, 20100.0,
    0.0,            -- ingen energi leveret
    0.6100,
    0.00,
    0.00,
    'Fault',
    NOW()
);

-- ──────────────────────────────────────────────
-- 4. Afsluttet nat-session — ingen idle fee (udenfor spidstid)
-- ──────────────────────────────────────────────
INSERT INTO charging_sessions VALUES (
    'demo-sess-004',
    'DEMO-CHR-003', 'CON-C', 'CONTRACT-TAXI-12',
    'DK1', 'COMPLETED',
    '2024-06-10 23:00:00', '2024-06-11 03:30:00',
    5500.0, 5594.0,
    94.0,           -- stort batteri, 4.5t opladning om natten
    0.1800,         -- lav natpris
    0.00,           -- ingen idle fee — nat er IKKE spidstid
    16.92,          -- 94.0 × 0.18 = 16.92 DKK
    'Normal',
    NOW()
);

-- ──────────────────────────────────────────────
-- 5. Session i ACTIVE tilstand (i gang nu)
-- ──────────────────────────────────────────────
INSERT INTO charging_sessions VALUES (
    'demo-sess-005',
    'DEMO-CHR-002', 'CON-B', 'CONTRACT-FLEET-01',
    'DK2', 'ACTIVE',
    NOW(), NULL,
    33000.0, NULL,
    NULL,
    0.7500,
    NULL, NULL,
    NULL,
    NOW()
);

-- ──────────────────────────────────────────────
-- 6. Session der afventer autorisering
-- ──────────────────────────────────────────────
INSERT INTO charging_sessions VALUES (
    'demo-sess-006',
    'DEMO-CHR-004', 'CON-D', 'CONTRACT-PRIV-03',
    'DK1', 'PENDING',
    NOW(), NULL,
    NULL, NULL, NULL,
    0.6300,
    NULL, NULL, NULL,
    NOW()
);

-- ──────────────────────────────────────────────
-- Verificer indsatte rækker
-- ──────────────────────────────────────────────
SELECT
    session_id,
    charger_id,
    price_area,
    status,
    energy_delivered,
    spot_price_dkk,
    idle_fee,
    session_cost
FROM charging_sessions
WHERE charger_id LIKE 'DEMO-%'
ORDER BY created_at;
