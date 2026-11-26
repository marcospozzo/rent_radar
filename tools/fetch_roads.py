"""Downloads the AMBA's motorways and avenues from OpenStreetMap into data/roads.json.gz.

Run by hand when the roads file needs a refresh (roads change rarely), then
commit the result: the pipeline reads the file and never calls Overpass, a
shared public service with usage limits. Standard library only, so it runs with
any Python 3 on the host:

    python3 tools/fetch_roads.py

Road data © OpenStreetMap contributors, ODbL.
"""
from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Public Overpass instances, tried in turn: any of them can be at capacity for
# hours (HTTP 502, 504 or no answer), and all serve the same OpenStreetMap data.
# On 2026-11-26 the main one had answered 502 for a day while mail.ru's worked.
OVERPASS_URLS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OUTPUT = Path(__file__).resolve().parent.parent / "data" / "roads.json.gz"

# CABA and Gran Buenos Aires with room to spare: a listing near the edge of the
# box would otherwise measure against a road farther away than one left outside.
SOUTH, WEST, NORTH, EAST = -35.05, -58.95, -34.35, -58.15

# The box is asked in tiles: in one piece the query outlives Overpass's gateway
# (HTTP 502). A way crossing tiles comes back from each, whole, and is kept once.
TILES = 3
RETRIES = 6

# OSM classes, not the "Avenida" in a name: in GBA plenty of quiet streets are
# called avenida, and Avenida General Paz is a motorway. Trunk roads here are
# arterials such as Ruta 3 or 9 de Julio, so they count as avenues. Motorway
# ramps (motorway_link) are left out.
KINDS = {
    "motorway": "autopista",
    "trunk": "avenida",
    "primary": "avenida",
    "secondary": "avenida",
}

# Five decimals is about one metre, far finer than the listings' coordinates.
PRECISION = 5


def tiles() -> list[tuple[float, float, float, float]]:
    height = (NORTH - SOUTH) / TILES
    width = (EAST - WEST) / TILES
    return [
        (SOUTH + row * height, WEST + column * width, SOUTH + (row + 1) * height, WEST + (column + 1) * width)
        for row in range(TILES)
        for column in range(TILES)
    ]


def query(south: float, west: float, north: float, east: float) -> str:
    classes = "|".join(KINDS)
    return (
        "[out:json][timeout:180];"
        f'way["highway"~"^({classes})$"]({south:.4f},{west:.4f},{north:.4f},{east:.4f});'
        "out tags geom;"
    )


def fetch_tile(box: tuple[float, float, float, float]) -> list[dict]:
    body = urllib.parse.urlencode({"data": query(*box)}).encode()
    # A busy Overpass answers 502 or 429 and asks for exponential backoff; the
    # next attempt goes to the next instance.
    for attempt in range(RETRIES):
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
        request = urllib.request.Request(url, data=body, headers={"User-Agent": "rent-radar/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=210) as response:
                return json.load(response)["elements"]
        except urllib.error.HTTPError as error:
            if error.code not in (429, 502, 503, 504) or attempt == RETRIES - 1:
                raise
            problem = f"answered {error.code}"
        # A timeout or dropped connection: the instance is overloaded, not the query wrong.
        except OSError as error:
            if attempt == RETRIES - 1:
                raise
            problem = f"failed ({error})"
        wait = 15 * 2**attempt
        print(f"{url} {problem}; retrying in {wait} s", flush=True)
        time.sleep(wait)
    raise AssertionError("unreachable")


def fetch() -> list[dict]:
    ways: dict[int, dict] = {}
    for box in tiles():
        for element in fetch_tile(box):
            ways[element["id"]] = element
    return list(ways.values())


def road(element: dict) -> dict:
    tags = element["tags"]
    return {
        "kind": KINDS[tags["highway"]],
        "name": tags.get("name"),
        "points": [[round(p["lat"], PRECISION), round(p["lon"], PRECISION)] for p in element["geometry"]],
    }


def main() -> None:
    roads = [road(element) for element in fetch() if len(element.get("geometry", [])) >= 2]
    document = {
        "source": "OpenStreetMap contributors, ODbL",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bbox": [SOUTH, WEST, NORTH, EAST],
        "roads": roads,
    }
    OUTPUT.parent.mkdir(exist_ok=True)
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as file:
        json.dump(document, file, ensure_ascii=False, separators=(",", ":"))
    counts = {kind: sum(r["kind"] == kind for r in roads) for kind in set(KINDS.values())}
    print(f"{len(roads)} roads written to {OUTPUT} ({counts})")


if __name__ == "__main__":
    main()
