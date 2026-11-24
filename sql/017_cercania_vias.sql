-- Distance from each candidate listing to the nearest motorway and avenue, measured
-- once by jobs/measure_roads.py from the portal's coordinates. Kept per listing
-- rather than per alert so the thresholds can be tuned against past listings
-- before any alert filters on them.
--
-- A listing has a row only once it was measured: no row means no coordinates (or
-- outside the roads file). A NULL distance in a row means nothing of that kind
-- within the search radius (1 km).

CREATE TABLE IF NOT EXISTS silver.cercania_vias (
    fuente         TEXT NOT NULL,
    id_publicacion TEXT NOT NULL,
    autopista_m    INTEGER,
    autopista      TEXT,
    avenida_m      INTEGER,
    avenida        TEXT,
    medido_en      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (fuente, id_publicacion)
);
