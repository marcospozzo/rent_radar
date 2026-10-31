-- A run is one portal scraped for one search. NULL for runs made before searches
-- existed, which silver.publicaciones still treats as belonging to the portal.

ALTER TABLE raw.pipeline_runs ADD COLUMN IF NOT EXISTS id_busqueda TEXT;
