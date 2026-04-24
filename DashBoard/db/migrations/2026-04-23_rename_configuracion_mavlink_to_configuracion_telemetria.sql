-- Migration: rename legacy vehicle telemetry config table
-- Date: 2026-04-23
--
-- Goal:
-- - Rename configuracion_mavlink -> configuracion_telemetria
-- - Keep data and constraints intact
-- - Provide rollback SQL
--
-- Notes:
-- - Run this migration during a maintenance window.
-- - After UP migration, set VEHICLE_TELEMETRY_CONFIG_TABLE=configuracion_telemetria
--   in .env and restart dashboard service/app.

-- =============================================
-- UP
-- =============================================
BEGIN;

DO $$
BEGIN
    IF to_regclass('public.configuracion_mavlink') IS NOT NULL
       AND to_regclass('public.configuracion_telemetria') IS NULL THEN
        EXECUTE 'ALTER TABLE public.configuracion_mavlink RENAME TO configuracion_telemetria';
    END IF;
END $$;

COMMIT;


-- =============================================
-- DOWN (rollback)
-- =============================================
-- Uncomment and run only if rollback is required.
-- BEGIN;
--
-- DO $$
-- BEGIN
--     IF to_regclass('public.configuracion_telemetria') IS NOT NULL
--        AND to_regclass('public.configuracion_mavlink') IS NULL THEN
--         EXECUTE 'ALTER TABLE public.configuracion_telemetria RENAME TO configuracion_mavlink';
--     END IF;
-- END $$;
--
-- COMMIT;
