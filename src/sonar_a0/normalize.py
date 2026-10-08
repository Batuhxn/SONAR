from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup


def decimal_value(value, *, locale: str = "json") -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace("\u00a0", "")
    if locale == "tr":
        text = text.replace(".", "").replace(",", ".")
    try:
        number = Decimal(text)
        return number if number.is_finite() and number >= 0 else None
    except InvalidOperation:
        return None


def integer_value(value, *, positive: bool = False) -> int | None:
    number = decimal_value(value)
    if number is None or number != number.to_integral_value() or (positive and number <= 0):
        return None
    return int(number)


def string_value(value) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def mpn_match(query: str | None, mpn: str | None, candidate: str | None = None) -> str:
    if not query:
        return "not_requested"
    target = query.strip().upper()
    if mpn:
        actual = mpn.strip().upper()
        if actual == target:
            return "exact_mpn"
        if target in actual or actual in target:
            return "partial"
        return "none"
    if candidate and candidate.strip().upper() == target:
        return "unverified_candidate"
    return "unknown"


def title_candidate(title: str) -> str | None:
    """Observed first title token, never derived from the user's search query."""
    token = title.split()[0] if title.split() else ""
    if re.fullmatch(r"\d+(?:\.\d+)?(?:pf|nf|uf|mf|ohm|kohm|mohm|kg|v|a|w|mm|mh|uh)", token, re.I):
        return None
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.,+/_-]*", token) and re.search(r"[A-Za-z]", token) and re.search(r"\d", token):
        return token
    return None


def schema_products(soup: BeautifulSoup) -> list[dict]:
    products = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.get_text(), parse_float=Decimal)
        except (json.JSONDecodeError, ValueError):
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            for entry in node.get("@graph", [node]):
                if isinstance(entry, dict) and entry.get("@type") == "Product":
                    products.append(entry)
    return products


def stock_from_schema(value) -> str:
    token = str(value or "").rsplit("/", 1)[-1]
    return {"InStock": "in_stock", "OutOfStock": "out_of_stock", "SoldOut": "out_of_stock", "PreOrder": "preorder", "BackOrder": "backorder", "Discontinued": "discontinued"}.get(token, "unknown")


def is_stale(fetched_at: str, now: datetime | None = None, max_age_minutes: int = 15) -> bool:
    stamp = datetime.fromisoformat(fetched_at)
    if stamp.tzinfo is None:
        raise ValueError("retrieval timestamp must include a timezone")
    current = now or datetime.now(timezone.utc)
    return current - stamp > timedelta(minutes=max_age_minutes) or stamp > current + timedelta(minutes=1)
