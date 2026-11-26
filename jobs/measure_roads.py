"""Measures how far each new candidate listing is from a motorway, an avenue and a
main street.

Runs between dbt and send_alerts, so the alert of a new listing already carries
its distances. Each listing is measured once (see sql/017_cercania_vias.sql);
listings without coordinates are skipped and looked at again next cycle, in case
a later snapshot brings them.
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg2
import psycopg2.extras

from app.roads import AVENUE, MAIN_STREET, MOTORWAY, RoadIndex

ROADS_FILE = Path(__file__).resolve().parent.parent / "data" / "roads.json.gz"

FETCH_UNMEASURED = """
    SELECT DISTINCT ON (c.fuente, c.id_publicacion) c.fuente, c.id_publicacion, c.latitud, c.longitud
    FROM gold.candidatas c
    LEFT JOIN silver.cercania_vias v USING (fuente, id_publicacion)
    WHERE v.id_publicacion IS NULL AND c.latitud IS NOT NULL AND c.longitud IS NOT NULL
"""

INSERT_MEASURES = """
    INSERT INTO silver.cercania_vias (
        fuente, id_publicacion, autopista_m, autopista, avenida_m, avenida, calle_principal_m, calle_principal
    )
    VALUES %s
    ON CONFLICT DO NOTHING
"""


def main() -> None:
    roads = RoadIndex.from_file(ROADS_FILE)
    conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"])
    try:
        with conn, conn.cursor() as cur:
            cur.execute(FETCH_UNMEASURED)
            unmeasured = cur.fetchall()
            rows = []
            outside = 0
            for source, listing_id, latitude, longitude in unmeasured:
                latitude, longitude = float(latitude), float(longitude)
                # Outside the roads file the nearest road may be one it left out:
                # better no measure than a reassuring wrong one.
                if not roads.covers(latitude, longitude):
                    outside += 1
                    continue
                motorway = roads.nearest(MOTORWAY, latitude, longitude)
                avenue = roads.nearest(AVENUE, latitude, longitude)
                main_street = roads.nearest(MAIN_STREET, latitude, longitude)
                rows.append((
                    source, listing_id,
                    motorway and motorway.distance_m, motorway and motorway.name,
                    avenue and avenue.distance_m, avenue and avenue.name,
                    main_street and main_street.distance_m, main_street and main_street.name,
                ))
            if rows:
                psycopg2.extras.execute_values(cur, INSERT_MEASURES, rows)
    finally:
        conn.close()
    print(f"{len(rows)} listings measured, {outside} outside the roads file")


if __name__ == "__main__":
    main()
