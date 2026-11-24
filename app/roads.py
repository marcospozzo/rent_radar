"""Distance from a point to the nearest motorway and avenue. Pure, no I/O but the file read.

The roads come from data/roads.json.gz (see tools/fetch_roads.py). Distances are
measured on a flat projection centred on Buenos Aires: across the AMBA its error
is well under a metre per hundred, far below the error of a listing's coordinates.
"""
from __future__ import annotations

import gzip
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

MOTORWAY = "autopista"
AVENUE = "avenida"

# Farther than this the answer is just "far": nobody minds a motorway 2 km away,
# and capping the search keeps it to a few grid cells.
SEARCH_RADIUS_M = 1000
_CELL_M = 500

_ORIGIN_LAT = -34.6
_ORIGIN_LON = -58.45
_M_PER_DEGREE_LAT = 110_574
_M_PER_DEGREE_LON = 111_320 * math.cos(math.radians(_ORIGIN_LAT))

Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class Nearest:
    distance_m: int
    name: str | None


@dataclass(frozen=True, slots=True)
class _Segment:
    start: Point
    end: Point
    name: str | None


def _project(latitude: float, longitude: float) -> Point:
    return (
        (longitude - _ORIGIN_LON) * _M_PER_DEGREE_LON,
        (latitude - _ORIGIN_LAT) * _M_PER_DEGREE_LAT,
    )


def _distance_to_segment(point: Point, segment: _Segment) -> float:
    (px, py), (ax, ay), (bx, by) = point, segment.start, segment.end
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    t = 0.0 if length_squared == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_squared))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _cell(value: float) -> int:
    return math.floor(value / _CELL_M)


class _KindIndex:
    """The segments of one kind of road, bucketed in a grid so a lookup reads only nearby cells."""

    def __init__(self) -> None:
        self._cells: dict[tuple[int, int], list[_Segment]] = defaultdict(list)

    def add(self, segment: _Segment) -> None:
        (ax, ay), (bx, by) = segment.start, segment.end
        for column in range(_cell(min(ax, bx)), _cell(max(ax, bx)) + 1):
            for row in range(_cell(min(ay, by)), _cell(max(ay, by)) + 1):
                self._cells[(column, row)].append(segment)

    def nearest(self, point: Point) -> Nearest | None:
        x, y = point
        reach = math.ceil(SEARCH_RADIUS_M / _CELL_M)
        best: tuple[float, str | None] | None = None
        for column in range(_cell(x) - reach, _cell(x) + reach + 1):
            for row in range(_cell(y) - reach, _cell(y) + reach + 1):
                for segment in self._cells.get((column, row), ()):
                    distance = _distance_to_segment(point, segment)
                    if best is None or distance < best[0]:
                        best = (distance, segment.name)
        if best is None or best[0] > SEARCH_RADIUS_M:
            return None
        return Nearest(distance_m=round(best[0]), name=best[1])


class RoadIndex:
    def __init__(self, roads: list[dict], bbox: list[float]) -> None:
        self._bbox = bbox
        self._kinds: dict[str, _KindIndex] = {MOTORWAY: _KindIndex(), AVENUE: _KindIndex()}
        for road in roads:
            points = [_project(latitude, longitude) for latitude, longitude in road["points"]]
            index = self._kinds[road["kind"]]
            for start, end in zip(points, points[1:]):
                index.add(_Segment(start, end, road["name"]))

    @classmethod
    def from_file(cls, path: Path) -> RoadIndex:
        with gzip.open(path, "rt", encoding="utf-8") as file:
            document = json.load(file)
        return cls(document["roads"], document["bbox"])

    def covers(self, latitude: float, longitude: float) -> bool:
        south, west, north, east = self._bbox
        return south <= latitude <= north and west <= longitude <= east

    def nearest(self, kind: str, latitude: float, longitude: float) -> Nearest | None:
        """The nearest road of this kind, or None when there is none within SEARCH_RADIUS_M."""
        return self._kinds[kind].nearest(_project(latitude, longitude))
