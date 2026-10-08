from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class Status(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    NOT_FOUND = "not_found"
    BLOCKED = "blocked"
    ROBOTS_DISALLOWED = "robots_disallowed"
    ROBOTS_UNAVAILABLE = "robots_unavailable"
    TIMEOUT = "timeout"
    HTTP_ERROR = "http_error"
    NETWORK_ERROR = "network_error"
    PARSE_ERROR = "parse_error"
    RATE_LIMITED = "rate_limited"
    SKIPPED = "skipped"


@dataclass
class PriceBreak:
    min_quantity: int
    unit_price: Decimal
    currency: str
    vat: str = "unknown"
    max_quantity: int | None = None
    packaging: str | None = None
    source: str = ""


@dataclass
class Offer:
    supplier: str
    url: str
    fetched_at: str
    title: str
    sku: str | None = None
    mpn: str | None = None
    manufacturer: str | None = None
    manufacturer_status: str = "unknown"
    candidate_mpn: str | None = None
    match: str = "unknown"
    package: str | None = None
    packaging: str | None = None
    stock_status: str = "unknown"
    stock_quantity: int | None = None
    moq: int | None = None
    order_multiple: int | None = None
    mpq: int | None = None
    prices: list[PriceBreak] = field(default_factory=list)
    field_sources: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Result:
    supplier: str
    operation: str
    query: str | None
    status: Status
    offers: list[Offer] = field(default_factory=list)
    message: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, dict):
                return {key: convert(item) for key, item in value.items()}
            if isinstance(value, list):
                return [convert(item) for item in value]
            return value
        return convert(asdict(self))
