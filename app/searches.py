"""Alert definitions: what Marc is looking for, loaded from alerts.yaml."""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# Relative to the working directory, which is /app for every job in the image.
ALERTS_FILE = Path(os.environ.get("ALERTS_FILE", "alerts.yaml"))
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


class Delivery(str, Enum):
    DIGEST = "digest"  # one email per cycle with everything new
    EACH = "each"  # one email per listing


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


class BothPrices(_Strict):
    rent: Price
    sale: Price


class PortalConfig(_Strict):
    max_pages: int = Field(default=20, ge=1)
    urls: list[str] = Field(default_factory=list)


class Search(_Strict):
    """One operation looked up on the portals: what the pipeline actually runs."""

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    alert_id: str
    delivery: Delivery
    operation: Operation
    active: bool = True
    neighborhoods: list[str] = Field(min_length=1)
    property_types: list[PropertyType] = Field(min_length=1)
    rooms: Rooms
    min_garage: int = Field(default=0, ge=0)
    min_area_m2: int | None = Field(default=None, gt=0)
    price: Price
    portals: dict[Portal, PortalConfig] = Field(min_length=1)


class Alert(_Strict):
    """What alerts.yaml asks for. An alert on `both` operations becomes two searches."""

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    operation: Literal["rent", "sale", "both"]
    delivery: Delivery = Delivery.DIGEST
    active: bool = True
    neighborhoods: list[str] = Field(min_length=1)
    property_types: list[PropertyType] = Field(min_length=1)
    rooms: Rooms
    min_garage: int = Field(default=0, ge=0)
    min_area_m2: int | None = Field(default=None, gt=0)
    price: Price | BothPrices
    portals: dict[Portal, PortalConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def _operation_matches_the_rest(self) -> Alert:
        both = self.operation == "both"
        if both and not isinstance(self.price, BothPrices):
            raise ValueError("operation 'both' needs a price for each: price: { rent: {...}, sale: {...} }")
        if not both and isinstance(self.price, BothPrices):
            raise ValueError(f"operation '{self.operation}' takes one price, not a rent and sale pair")
        if both and any(portal.urls for portal in self.portals.values()):
            raise ValueError(
                "operation 'both' cannot use portals.<portal>.urls, because a pasted URL is for "
                "one operation; make one alert for rent and another for sale"
            )
        return self

    def searches(self) -> list[Search]:
        if isinstance(self.price, BothPrices):
            return [
                self._search(Operation.RENT, self.price.rent),
                self._search(Operation.SALE, self.price.sale),
            ]
        return [self._search(Operation(self.operation), self.price)]

    def _search(self, operation: Operation, price: Price) -> Search:
        # Rent and sale prices are never mixed: each operation is its own search,
        # with its own runs and its own criteria.
        search_id = f"{self.id}-{operation.value}" if self.operation == "both" else self.id
        return Search(
            id=search_id,
            alert_id=self.id,
            delivery=self.delivery,
            operation=operation,
            active=self.active,
            neighborhoods=self.neighborhoods,
            property_types=self.property_types,
            rooms=self.rooms,
            min_garage=self.min_garage,
            min_area_m2=self.min_area_m2,
            price=price,
            portals=self.portals,
        )


class Neighborhood(_Strict):
    name: str
    zonaprop: str
    argenprop: str


class AppriseService(_Strict):
    # The Apprise URL carries a password, so it lives in a file outside the repo
    # and the YAML only points at it.
    url_file: str
    label: str | None = None


class AppriseConfig(_Strict):
    services: list[AppriseService] = Field(min_length=1)


class HealthConfig(_Strict):
    enabled: bool = True


class _AlertsFile(_Strict):
    apprise: AppriseConfig
    health: HealthConfig = Field(default_factory=HealthConfig)
    alerts: list[Alert]


class Config(_Strict):
    apprise: AppriseConfig
    health: HealthConfig
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


def load_config(
    alerts_path: Path = ALERTS_FILE,
    neighborhoods_path: Path = NEIGHBORHOODS_FILE,
) -> Config:
    try:
        parsed = _AlertsFile.model_validate(_read_yaml(alerts_path))
    except ValidationError as exc:
        raise SearchConfigError(f"{alerts_path}: {_describe(exc)}") from exc
    alerts = parsed.alerts

    known_neighborhoods = load_neighborhoods(neighborhoods_path)
    seen_ids: set[str] = set()
    searches: list[Search] = []
    for alert in alerts:
        for neighborhood in alert.neighborhoods:
            if neighborhood not in known_neighborhoods:
                raise SearchConfigError(
                    f"{alerts_path}: alert '{alert.id}' uses neighborhood '{neighborhood}', "
                    f"which is not in {neighborhoods_path} "
                    f"(known: {', '.join(sorted(known_neighborhoods))})"
                )
        for search in alert.searches():
            if search.id in seen_ids:
                raise SearchConfigError(f"{alerts_path}: id '{search.id}' appears more than once")
            seen_ids.add(search.id)
            searches.append(search)
    return Config(apprise=parsed.apprise, health=parsed.health, searches=searches)
