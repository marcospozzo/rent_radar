"""Copies the searches in alerts.yaml into silver.busquedas.

Run at the start of every cycle so an edit to the YAML takes effect on the next
run. A search removed from the file is marked inactive rather than deleted: the
listings and runs that refer to it stay explainable.
"""
from __future__ import annotations

import os
import sys

import psycopg2
import psycopg2.extras

from app.searches import Search, SearchConfigError, load_searches


def _row(search: Search) -> tuple[object, ...]:
    return (
        search.id,
        search.operation.value,
        search.active,
        search.price.currency,
        search.price.max,
        search.rooms.min,
        search.rooms.max,
        search.min_garage,
        search.min_area_m2,
    )


def main() -> None:
    try:
        searches = load_searches()
    except SearchConfigError as exc:
        sys.exit(f"Invalid search configuration: {exc}")

    conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"])
    try:
        with conn, conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO silver.busquedas
                    (id_busqueda, operacion, activa, moneda, precio_max,
                     ambientes_min, ambientes_max, cocheras_min, superficie_min_m2)
                VALUES %s
                ON CONFLICT (id_busqueda) DO UPDATE SET
                    operacion         = EXCLUDED.operacion,
                    activa            = EXCLUDED.activa,
                    moneda            = EXCLUDED.moneda,
                    precio_max        = EXCLUDED.precio_max,
                    ambientes_min     = EXCLUDED.ambientes_min,
                    ambientes_max     = EXCLUDED.ambientes_max,
                    cocheras_min      = EXCLUDED.cocheras_min,
                    superficie_min_m2 = EXCLUDED.superficie_min_m2,
                    actualizado_en    = now()
                """,
                [_row(search) for search in searches],
            )
            cur.execute(
                """
                UPDATE silver.busquedas
                SET activa = FALSE, actualizado_en = now()
                WHERE activa AND id_busqueda <> ALL(%s)
                """,
                ([search.id for search in searches],),
            )
            retired = cur.rowcount
    finally:
        conn.close()

    active = sum(1 for search in searches if search.active)
    print(f"{len(searches)} searches synced ({active} active, {retired} retired)")


if __name__ == "__main__":
    main()
