-- Listings already seen for each search and portal, and whether their alert was
-- sent. A listing is new for an alert when it has no row here yet.
--
-- The first listings of a search on a portal are inserted already marked as sent,
-- so a new alert (or a portal coming back from a long block) does not email
-- everything that already existed. enviado_en stays NULL until Apprise accepts the
-- message, so a failed send is retried on the next cycle.

CREATE TABLE IF NOT EXISTS silver.avisos (
    id_busqueda    TEXT NOT NULL,
    fuente         TEXT NOT NULL,
    id_publicacion TEXT NOT NULL,
    visto_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    enviado_en     TIMESTAMPTZ,
    PRIMARY KEY (id_busqueda, fuente, id_publicacion)
);

CREATE INDEX IF NOT EXISTS avisos_pendientes_idx
    ON silver.avisos (visto_en)
    WHERE enviado_en IS NULL;
