from __future__ import annotations

import csv
import io
import json
from decimal import Decimal

from .bom import Component


def selected_offer(component: Component) -> dict | None:
    if not component.choice:
        return None
    result = component.results.get(component.choice["supplier"], {})
    offers = result.get("offers", [])
    index = component.choice["offer"]
    return offers[index] if 0 <= index < len(offers) else None


def line(component: Component, bom_name: str, boards: int = 1, bom_id: str = "", source_filename: str = "") -> dict:
    offer = selected_offer(component)
    required = component.required
    result = {"bom": bom_name, "bom_id": bom_id, "source_filename": source_filename, "pcbs": boards, "component_id": component.id, "name": component.name, "mpn": component.mpn,
              "references": component.references, "quantity_per_pcb": component.quantity, "dnp": component.dnp,
              "required": required, "supplier": "Unassigned", "url": "", "title": "", "match": "unknown",
              "order_quantity": None, "unit_price": None, "known_cost": None, "currency": "", "vat": "unknown",
              "stock_status": "unknown", "stock_quantity": None, "fetched_at": "", "packaging": None,
              "warnings": list(component.issues), "raw": component.raw}
    if component.dnp is True or not component.selected:
        result["warnings"].append("Excluded from procurement")
        return result
    if not offer:
        result["warnings"].append("No supplier product selected")
        return result
    result.update({key: offer.get(key) for key in ("supplier", "url", "title", "match", "stock_status", "stock_quantity", "fetched_at")})
    result["warnings"] += offer.get("warnings", [])
    if offer.get("match") != "exact_mpn":
        result["warnings"].append("Unverified match: engineering review required")
    prices = offer.get("prices", [])
    tier = component.choice["tier"]
    price = prices[tier] if 0 <= tier < len(prices) else None
    if required is None:
        result["warnings"].append("Resolve quantity / DNP before calculating cost")
        return result
    minimum = max(required, offer.get("moq") or 1, price["min_quantity"] if price else 1)
    multiple = offer.get("order_multiple") or 1
    order = ((minimum + multiple - 1) // multiple) * multiple
    result["order_quantity"] = order
    if order != required:
        result["warnings"].append("Order quantity increased for selected tier / MOQ / order multiple")
    if price:
        result.update({"unit_price": price["unit_price"], "currency": price["currency"], "vat": price.get("vat", "unknown"),
                       "packaging": price.get("packaging") or offer.get("packaging")})
        if price.get("max_quantity") is not None and order > price["max_quantity"]:
            result["warnings"].append("Order exceeds selected price tier; cost unavailable")
        else:
            result["known_cost"] = str(Decimal(price["unit_price"]) * order)
    else:
        result["warnings"].append("Price unavailable; cost not included in totals")
    if offer.get("stock_quantity") is not None and offer["stock_quantity"] < order:
        result["warnings"].append("Reported stock is insufficient")
    if offer.get("stock_status") != "in_stock":
        result["warnings"].append("Availability requires confirmation")
    if result["vat"] == "unknown":
        result["warnings"].append("VAT basis unknown")
    return result


def procurement(boms: dict) -> dict:
    lines = [line(c, b["name"], b["boards"], bid, b.get("filename", "")) for bid, b in boms.items() for c in b["components"] if c.selected and c.dnp is not True]
    totals: dict[tuple, Decimal] = {}
    for item in lines:
        if item["known_cost"] is not None:
            key = (item["supplier"], item["currency"], item["vat"])
            totals[key] = totals.get(key, Decimal(0)) + Decimal(item["known_cost"])
    return {"lines": lines, "totals": [{"supplier": k[0], "currency": k[1], "vat": k[2], "amount": str(v)} for k, v in totals.items()],
            "missing_costs": sum(item["known_cost"] is None for item in lines),
            "note": "Known item costs only. Currencies and VAT bases remain separate. Shipping, currency conversion and unspecified taxes are excluded."}


def csv_safe(value) -> str:
    value = "" if value is None else str(value)
    # Protect spreadsheet consumers against formulas, including leading whitespace.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")) else value


def export_csv(lines: list[dict]) -> bytes:
    fields = ["bom", "bom_id", "source_filename", "component_id", "pcbs", "name", "mpn", "references", "quantity_per_pcb", "dnp", "required", "supplier", "title", "url",
              "match", "order_quantity", "unit_price", "currency", "vat", "known_cost", "packaging", "stock_status",
              "stock_quantity", "fetched_at", "warnings", "source_fields"]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for item in lines:
        row = {k: item.get(k) for k in fields}
        row.update(warnings="; ".join(item["warnings"]), source_fields=json.dumps(item["raw"], ensure_ascii=False))
        writer.writerow({k: csv_safe(v) for k, v in row.items()})
    return output.getvalue().encode("utf-8-sig")
