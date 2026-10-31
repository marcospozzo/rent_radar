-- Searches defined in searches.yaml, copied here by jobs/sync_searches.py so dbt
-- can filter each search's listings by its own criteria. The YAML is the source
-- of truth; rows missing from it are kept but marked inactive.

CREATE TABLE IF NOT EXISTS silver.busquedas (
    id_busqueda       TEXT PRIMARY KEY,
    operacion         TEXT NOT NULL CHECK (operacion IN ('rent', 'sale')),
    activa            BOOLEAN NOT NULL,
    moneda            TEXT NOT NULL CHECK (moneda IN ('ARS', 'USD')),
    precio_max        NUMERIC,
    ambientes_min     INTEGER NOT NULL,
    ambientes_max     INTEGER,
    cocheras_min      INTEGER NOT NULL,
    superficie_min_m2 NUMERIC,
    actualizado_en    TIMESTAMPTZ NOT NULL DEFAULT now()
);
