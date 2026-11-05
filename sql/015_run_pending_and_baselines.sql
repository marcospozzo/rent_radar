-- ArgenProp reads the detail of only some new listings per run, so a search can
-- take several runs to see everything it matches. pendientes counts what a run
-- left for the next one.
--
-- A search's first listings are recorded without an email so a new alert does not
-- send everything that already exists. That baseline now lasts until a run of the
-- search and portal ends with nothing pending; lineas_base holds the pairs whose
-- baseline is over, and send_alerts sends only for those.

ALTER TABLE raw.pipeline_runs ADD COLUMN IF NOT EXISTS pendientes INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS silver.lineas_base (
    id_busqueda TEXT NOT NULL,
    fuente      TEXT NOT NULL,
    completa_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id_busqueda, fuente)
);

-- Pairs that already have listings recorded had their baseline taken in one run,
-- except ArgenProp, whose first runs only read part of the results: those stay
-- open until a run finishes with nothing pending.
INSERT INTO silver.lineas_base (id_busqueda, fuente)
SELECT DISTINCT id_busqueda, fuente FROM silver.avisos WHERE fuente <> 'argenprop'
ON CONFLICT DO NOTHING;
