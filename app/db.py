from __future__ import annotations

from typing import Any, Iterable

import psycopg2
import psycopg2.extras

from app.config import NEON_DATABASE_URL
from app.models import KnownDetail


class ScraperDB:
    def __init__(self) -> None:
        self.conn = self._connect()

    def _connect(self) -> psycopg2.extensions.connection:
        conn = psycopg2.connect(
            NEON_DATABASE_URL,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
        )
        psycopg2.extras.register_uuid(conn)
        return conn

    def _ensure_connected(self) -> None:
        if self.conn.closed:
            self.conn = self._connect()
            return
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")
        except Exception:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = self._connect()

    def close(self) -> None:
        if not self.conn.closed:
            self.conn.close()

    # ------------------------------------------------------------------- reads

    def known_details(self, source: str) -> dict[str, KnownDetail]:
        """The latest snapshot's detail of every listing of a portal still in raw.snapshots."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (id_publicacion)
                    id_publicacion, titulo, latitud, longitud, ambientes, dormitorios,
                    banos, superficie_m2, publicado_en, vendedor, especificaciones,
                    precio, moneda, expensas, ubicacion
                FROM raw.snapshots
                WHERE fuente = %s
                ORDER BY id_publicacion, fecha_scraping DESC
                """,
                (source,),
            )
            return {
                row[0]: KnownDetail(
                    title=row[1], latitude=row[2], longitude=row[3], rooms=row[4],
                    bedrooms=row[5], bathrooms=row[6], surface_m2=row[7],
                    published_at=row[8], seller=row[9], specifications=list(row[10] or []),
                    price=row[11], currency=row[12], expenses=row[13], location=row[14],
                )
                for row in cur.fetchall()
            }

    def last_run_was_complete(self, source: str, search_id: str | None) -> bool:
        """True if the latest good run of this search and portal left nothing unread.
        With no earlier run there is nothing to trust, so it is not complete."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT pendientes = 0 FROM raw.pipeline_runs
                WHERE fuente = %s AND id_busqueda IS NOT DISTINCT FROM %s AND estado = 'ok'
                ORDER BY finalizado_en DESC LIMIT 1
                """,
                (source, search_id),
            )
            row = cur.fetchone()
        return bool(row and row[0])

    # ------------------------------------------------------------------ writes

    def insert_run(self, row: dict[str, Any]) -> None:
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO raw.pipeline_runs
                    (id_ejecucion, id_busqueda, fuente, estado, iniciado_en, finalizado_en, total_publicaciones,
                     pendientes)
                VALUES
                    (%(id_ejecucion)s, %(id_busqueda)s, %(fuente)s, %(estado)s, %(iniciado_en)s,
                     %(finalizado_en)s, %(total_publicaciones)s, %(pendientes)s)
                ON CONFLICT (id_ejecucion) DO UPDATE
                    SET estado               = EXCLUDED.estado,
                        finalizado_en        = EXCLUDED.finalizado_en,
                        total_publicaciones  = EXCLUDED.total_publicaciones,
                        pendientes           = EXCLUDED.pendientes
                """,
                row,
            )
        self.conn.commit()

    def insert_snapshots(self, rows: Iterable[dict[str, Any]]) -> None:
        records = list(rows)
        if not records:
            return
        self._ensure_connected()
        with self.conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO raw.snapshots
                    (id_ejecucion, fuente, id_publicacion, url, titulo, precio, moneda,
                     expensas, ubicacion, latitud, longitud, ambientes, dormitorios,
                     banos, superficie_m2, publicado_en, fecha_scraping, vendedor, especificaciones)
                VALUES %s
                """,
                [
                    (
                        r["id_ejecucion"], r["fuente"], r["id_publicacion"], r["url"],
                        r["titulo"], r.get("precio"), r.get("moneda"), r.get("expensas"),
                        r.get("ubicacion"), r.get("latitud"), r.get("longitud"),
                        r.get("ambientes"), r.get("dormitorios"), r.get("banos"),
                        r.get("superficie_m2"), r.get("publicado_en"), r.get("fecha_scraping"),
                        r.get("vendedor"), r.get("especificaciones", []),
                    )
                    for r in records
                ],
            )
        self.conn.commit()
