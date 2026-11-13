"""Emails the new listings of each alert, and remembers what it already sent.

A listing is new for an alert when gold.candidatas has it and silver.avisos does
not (see sql/011_avisos.sql). Nothing is marked as sent unless Apprise accepted
the message, so a failed send is retried on the next cycle; the step then exits
with an error so the failure shows up in the run instead of being lost.
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from typing import TypedDict, cast

import psycopg2
import psycopg2.extras

from app.alert_format import NewListing, digest_message, single_message
from app.alerts import build_notifier, send
from app.searches import Delivery, Search, SearchConfigError, load_config

# Listings of a search and portal whose baseline is not over yet are recorded as
# already sent: that is the silent baseline.
RECORD_CANDIDATES = """
    INSERT INTO silver.avisos (id_busqueda, fuente, id_publicacion, enviado_en)
    SELECT c.id_busqueda, c.fuente, c.id_publicacion,
           CASE WHEN EXISTS (
                    SELECT 1 FROM silver.lineas_base l
                    WHERE l.id_busqueda = c.id_busqueda AND l.fuente = c.fuente
                ) THEN NULL ELSE now() END
    FROM gold.candidatas c
    ON CONFLICT DO NOTHING
"""

# Run after RECORD_CANDIDATES, so the cycle whose run finishes the baseline still
# records its own listings silently: they are part of what already existed. Sending
# starts with the next cycle.
END_BASELINES = """
    INSERT INTO silver.lineas_base (id_busqueda, fuente)
    SELECT id_busqueda, fuente FROM (
        SELECT DISTINCT ON (r.fuente, r.id_busqueda) r.id_busqueda, r.fuente, r.pendientes
        FROM raw.pipeline_runs r
        INNER JOIN silver.busquedas b ON b.id_busqueda = r.id_busqueda AND b.activa
        WHERE r.estado = 'ok'
        ORDER BY r.fuente, r.id_busqueda, r.finalizado_en DESC
    ) latest
    WHERE pendientes = 0
    ON CONFLICT DO NOTHING
"""

FETCH_PENDING = """
    SELECT a.id_busqueda, a.fuente, a.id_publicacion,
           c.titulo, c.url, c.precio, c.moneda, c.ubicacion, c.ambientes,
           coalesce(c.superficie_cubierta, c.superficie_total) AS superficie,
           c.cocheras, c.antiguedad
    FROM silver.avisos a
    JOIN gold.candidatas c USING (id_busqueda, fuente, id_publicacion)
    WHERE a.enviado_en IS NULL
    ORDER BY a.visto_en, a.fuente, a.id_publicacion
"""

MARK_SENT = """
    UPDATE silver.avisos SET enviado_en = now()
    WHERE (id_busqueda, fuente, id_publicacion) IN %s
"""

Key = tuple[str, str, str]
Number = Decimal | int | None


class PendingRow(TypedDict):
    id_busqueda: str
    fuente: str
    id_publicacion: str
    titulo: str | None
    url: str
    precio: Number
    moneda: str | None
    ubicacion: str | None
    ambientes: Number
    superficie: Number
    cocheras: Number
    antiguedad: Number


def _number(value: Number) -> float | None:
    return None if value is None else float(value)


def _whole(value: Number) -> int | None:
    return None if value is None else int(value)


def _listing(row: PendingRow, search: Search) -> NewListing:
    return NewListing(
        operation=search.operation,
        source=row["fuente"],
        title=row["titulo"] or "Publicación sin título",
        url=row["url"],
        price=_number(row["precio"]),
        currency=row["moneda"],
        location=row["ubicacion"],
        rooms=_whole(row["ambientes"]),
        area_m2=_number(row["superficie"]),
        garage=_whole(row["cocheras"]),
        age_years=_whole(row["antiguedad"]),
    )


def main() -> None:
    try:
        config = load_config()
        # One notifier per distinct list of recipients; built up front so a bad
        # configuration fails before anything is sent.
        notifiers = {
            tuple(search.to): build_notifier(config.apprise.services, search.to)
            for search in config.searches
        }
    except SearchConfigError as exc:
        sys.exit(f"Invalid alert configuration: {exc}")
    searches = {search.id: search for search in config.searches}

    conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"])
    try:
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(RECORD_CANDIDATES)
            recorded = cur.rowcount
            cur.execute(END_BASELINES)
            cur.execute(FETCH_PENDING)
            pending = cast(list[PendingRow], cur.fetchall())

        # search id -> [(key, listing)]. A pending row whose search left the config
        # stays pending until the search comes back.
        by_search: dict[str, list[tuple[Key, NewListing]]] = {}
        for row in pending:
            search = searches.get(row["id_busqueda"])
            if search is None:
                continue
            key = (row["id_busqueda"], row["fuente"], row["id_publicacion"])
            by_search.setdefault(search.id, []).append((key, _listing(row, search)))

        emails = failures = 0
        for search_id, items in by_search.items():
            search = searches[search_id]
            batches = [items] if search.delivery is Delivery.DIGEST else [[item] for item in items]
            for batch in batches:
                listings = [listing for _, listing in batch]
                title, body = (
                    digest_message(search.id, search.operation, listings)
                    if search.delivery is Delivery.DIGEST
                    else single_message(search.id, listings[0])
                )
                if send(notifiers[tuple(search.to)], title, body):
                    with conn, conn.cursor() as cur:
                        cur.execute(MARK_SENT, (tuple(key for key, _ in batch),))
                    emails += 1
                else:
                    failures += 1
                    print(f"Could not send '{title}'; it will be retried next cycle")
    finally:
        conn.close()

    print(f"{recorded} listings recorded, {emails} emails sent, {failures} failed")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
