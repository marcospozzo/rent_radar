-- Distance to the nearest main street (OpenStreetMap tertiary roads), next to the
-- motorway and avenue ones.
--
-- The rows measured before this column existed are deleted rather than left with
-- a NULL distance, which would read as "no main street within 1 km". Nothing is
-- lost: jobs/measure_roads.py measures every candidate without a row again on the
-- next cycle, from the coordinates already stored.

ALTER TABLE silver.cercania_vias
    ADD COLUMN IF NOT EXISTS calle_principal_m INTEGER,
    ADD COLUMN IF NOT EXISTS calle_principal   TEXT;

DELETE FROM silver.cercania_vias;
