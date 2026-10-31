"""Applies the SQL files in sql/ that this database has not seen yet.

Postgres runs docker-entrypoint-initdb.d only on an empty data volume, so a
schema change would never reach an existing volume. Applied files are recorded
in public.schema_migrations. Each file runs in its own transaction together
with its record, so a failing migration leaves nothing half-applied.
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg2

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "sql"


def pending_migrations(applied: set[str]) -> list[Path]:
    return [path for path in sorted(MIGRATIONS_DIR.glob("*.sql")) if path.name not in applied]


def main() -> None:
    conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"])
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public.schema_migrations (
                    filename   TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute("SELECT filename FROM public.schema_migrations")
            applied = {row[0] for row in cur.fetchall()}

        pending = pending_migrations(applied)
        for path in pending:
            with conn, conn.cursor() as cur:
                cur.execute(path.read_text())
                cur.execute("INSERT INTO public.schema_migrations (filename) VALUES (%s)", (path.name,))
            print(f"applied {path.name}")
        if not pending:
            print("schema is up to date")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
