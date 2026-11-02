-- Without the map there is no reason to fix a portal's wrong coordinates:
-- geocode_fallback.py is gone, and with it the corrections it stored
-- (silver.coordenadas_override) and its "could not locate" notices
-- (silver.coordenadas_no_resueltas).
--
-- silver.publicaciones_rechazadas was an audit copy of the filters in
-- silver.publicaciones that had drifted from it (other price limits, no duplicate
-- or commercial-use check) and nothing read it once the geocoding step went.
-- It is built by dbt, which does not drop a removed model.

DROP TABLE IF EXISTS silver.coordenadas_no_resueltas;
DROP TABLE IF EXISTS silver.coordenadas_override;
DROP TABLE IF EXISTS silver.publicaciones_rechazadas;
