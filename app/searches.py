"""Search definitions: what Marc is looking for, loaded from searches.yaml."""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# Relative to the working directory, which is /app for every job in the image.
SEARCHES_FILE = Path(os.environ.get("SEARCHES_FILE", "searches.yaml"))
NEIGHBORHOODS_FILE = Path(os.environ.get("NEIGHBORHOODS_FILE", "neighborhoods.yaml"))

Portal = Literal["zonaprop", "argenprop", "mercadolibre"]
PropertyType = Literal["casa", "departamento", "ph"]


class SearchConfigError(Exception):
    """The configuration is wrong in a way the message tells how to fix."""


class _Strict(BaseModel):
    # A misspelled key must fail loudly instead of being silently ignored.
    model_config = ConfigDict(extra="forbid")


class Operation(str, Enum):
    RENT = "rent"
    SALE = "sale"


class Rooms(_Strict):
    min: int = Field(ge=1)
    max: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _max_not_below_min(self) -> Rooms:
        if self.max is not None and self.max < self.min:
            raise ValueError("rooms.max is lower than rooms.min")
        return self


class Price(_Strict):
    currency: Literal["ARS", "USD"]
    max: int | None = Field(default=None, gt=0)


class PortalConfig(_Strict):
    max_pages: int = Field(default=20, ge=1)
    urls: list[str] = Field(default_factory=list)


class Search(_Strict):
    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    operation: Operation
    active: bool = True
    neighborhoods: list[str] = Field(min_length=1)
    property_types: list[PropertyType] = Field(min_length=1)
    rooms: Rooms
    min_garage: int = Field(default=0, ge=0)
    min_area_m2: int | None = Field(default=None, gt=0)
    price: Price
    portals: dict[Portal, PortalConfig] = Field(min_length=1)


class Neighborhood(_Strict):
    name: str
    zonaprop: str
    argenprop: str


class _SearchesFile(_Strict):
    searches: list[Search]


def _read_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SearchConfigError(f"Cannot read {path}: {exc.strerror}") from exc
    except yaml.YAMLError as exc:
        raise SearchConfigError(f"{path} is not valid YAML: {exc}") from exc


def _describe(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()
    )


def load_neighborhoods(path: Path = NEIGHBORHOODS_FILE) -> dict[str, Neighborhood]:
    raw = _read_yaml(path)
    if not isinstance(raw, dict):
        raise SearchConfigError(f"{path} must map each neighborhood key to its portal names")
    try:
        return {key: Neighborhood.model_validate(value) for key, value in raw.items()}
    except ValidationError as exc:
        raise SearchConfigError(f"{path}: {_describe(exc)}") from exc


def load_searches(
    searches_path: Path = SEARCHES_FILE,
    neighborhoods_path: Path = NEIGHBORHOODS_FILE,
) -> list[Search]:
    try:
        searches = _SearchesFile.model_validate(_read_yaml(searches_path)).searches
    except ValidationError as exc:
        raise SearchConfigError(f"{searches_path}: {_describe(exc)}") from exc

    known_neighborhoods = load_neighborhoods(neighborhoods_path)
    seen_ids: set[str] = set()
    for search in searches:
        if search.id in seen_ids:
            raise SearchConfigError(f"{searches_path}: search id '{search.id}' appears more than once")
        seen_ids.add(search.id)
        for neighborhood in search.neighborhoods:
            if neighborhood not in known_neighborhoods:
                raise SearchConfigError(
                    f"{searches_path}: search '{search.id}' uses neighborhood '{neighborhood}', "
                    f"which is not in {neighborhoods_path} "
                    f"(known: {', '.join(sorted(known_neighborhoods))})"
                )

    # dbt already keeps searches apart, but event detection takes the last two
    # runs of a portal, which would be runs of different searches, and the
    # dashboard would list a property once per search. Refuse rather than let
    # both go wrong silently; lift this when they work per search.
    active_ids = [search.id for search in searches if search.active]
    if len(active_ids) > 1:
        raise SearchConfigError(
            f"{searches_path}: {len(active_ids)} searches are active ({', '.join(active_ids)}), "
            "but events and the dashboard support only one for now; set `active: false` on the others"
        )
    return searches
