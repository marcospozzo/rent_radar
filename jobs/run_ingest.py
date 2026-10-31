"""
Corre los spiders para cada busqueda activa de searches.yaml.

Una corrida es un portal scrapeado para una busqueda (main.py --ingest). Los
portales corren en paralelo entre si, pero las busquedas de un mismo portal van
una detras de otra: es lo que mantiene bajo el ritmo de pedidos a cada portal.
Las URLs de cada portal son las escritas en la busqueda o las generadas a partir
de ella.
"""
from __future__ import annotations

import select
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import get_args

from app.searches import Portal, SearchConfigError, load_neighborhoods, load_searches
from spiders.urls import build_portal_urls

INACTIVITY_TIMEOUT = 120  # segundos sin output → proceso colgado


@dataclass
class IngestJob:
    portal: str
    search_id: str
    urls: list[str]
    max_pages: int
    # Barrios que la pagina de resultados debe nombrar. Vacio si las URLs se
    # escribieron a mano: ahi no sabemos que barrios cubren.
    expected_names: list[str]


def build_jobs(only_portal: str | None) -> list[IngestJob]:
    neighborhoods = load_neighborhoods()
    jobs: list[IngestJob] = []
    for search in load_searches():
        if not search.active:
            continue
        for portal, portal_config in search.portals.items():
            if only_portal and portal != only_portal:
                continue
            generated = not portal_config.urls
            jobs.append(
                IngestJob(
                    portal=portal,
                    search_id=search.id,
                    urls=build_portal_urls(portal, search, neighborhoods),
                    max_pages=portal_config.max_pages,
                    expected_names=[neighborhoods[key].name for key in search.neighborhoods] if generated else [],
                )
            )
    return jobs


def _run_job(job: IngestJob) -> int:
    label = f"{job.portal}/{job.search_id}"
    cmd = [sys.executable, "main.py", "--ingest", "--source", job.portal, "--search-id", job.search_id]
    for url in job.urls:
        cmd += ["--start-url", url]
    for name in job.expected_names:
        cmd += ["--expect-name", name]
    cmd += ["--max-pages", str(job.max_pages)]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    while True:
        ready, _, _ = select.select([proc.stdout], [], [], INACTIVITY_TIMEOUT)
        if ready:
            line = proc.stdout.readline()
            if not line:  # EOF — proceso terminó
                break
            print(f"[{label}] {line}", end="", flush=True)
        else:
            print(
                f"\n[{label}] Sin actividad por {INACTIVITY_TIMEOUT}s — proceso colgado, matando",
                flush=True,
            )
            proc.kill()
            proc.wait()
            return 1

    proc.wait()
    return proc.returncode


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=None, help="Correr solo este portal (zonaprop|argenprop|mercadolibre)")
    args = parser.parse_args()

    portals = get_args(Portal)
    if args.source and args.source not in portals:
        print(f"Fuente desconocida: {args.source}. Opciones: {list(portals)}")
        sys.exit(1)

    try:
        jobs = build_jobs(args.source)
    except SearchConfigError as exc:
        sys.exit(f"Configuracion de busquedas invalida: {exc}")

    if not jobs:
        print("No hay busquedas activas para correr (ver searches.yaml).")
        sys.exit(1)

    jobs_by_portal: dict[str, list[IngestJob]] = {}
    for job in jobs:
        jobs_by_portal.setdefault(job.portal, []).append(job)

    results: dict[str, int] = {}

    def _run_portal(portal_jobs: list[IngestJob]) -> None:
        for job in portal_jobs:
            results[f"{job.portal}/{job.search_id}"] = _run_job(job)

    threads = [
        threading.Thread(target=_run_portal, args=(portal_jobs,), name=portal)
        for portal, portal_jobs in jobs_by_portal.items()
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print("\n--- Resultado ---")
    ok = True
    for name, code in results.items():
        status = "OK" if code == 0 else f"ERROR (exit {code})"
        print(f"  {name}: {status}")
        if code != 0:
            ok = False

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
