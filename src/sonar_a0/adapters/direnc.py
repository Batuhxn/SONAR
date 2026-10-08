from __future__ import annotations

import re
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from ..models import Offer, PriceBreak, Result, Status
from ..normalize import decimal_value, integer_value, mpn_match, schema_products, stock_from_schema, string_value, title_candidate
from ..transport import Document, FetchError
from .base import SupplierAdapter


class DirencAdapter(SupplierAdapter):
    name = "direnc"
    hosts = {"www.direnc.net", "direnc.net"}

    def search(self, mpn: str, *, limit: int = 5) -> Result:
        if not mpn.strip() or not 1 <= limit <= 20:
            raise ValueError("A nonempty query and limit 1..20 are required")
        url = "https://www.direnc.net/arama?" + urlencode({"q": mpn})
        start = len(self.client.evidence)
        try:
            document = self.client.get(url)
            soup = BeautifulSoup(document.text, "html.parser")
            urls = []
            for card in soup.select('.cardItem[data-toggle="product"]'):
                link = card.select_one('a[data-toggle="product-url"][href]')
                if link:
                    found = urljoin(document.url, link["href"])
                    self.client.validate_url(found)
                    if found not in urls:
                        urls.append(found)
            if not urls:
                if "ilgili ürün bulunamadı" in soup.get_text(" ", strip=True) or "Bu listede şu anda ürün bulunmamaktadır" in soup.get_text(" ", strip=True):
                    result = Result(self.name, "search", mpn, Status.NOT_FOUND, message="Supplier explicitly reports no search results")
                else:
                    result = Result(self.name, "search", mpn, Status.PARSE_ERROR, message="Search format changed or results not server-rendered")
            else:
                result = Result(self.name, "search", mpn, Status.OK)
                problems = []
                for found in urls[:limit]:
                    item = self.product(found, mpn=mpn)
                    result.offers.extend(item.offers)
                    if item.status != Status.OK:
                        problems.append(f"{found}: {item.status} {item.message}")
                    if item.status in {Status.BLOCKED, Status.RATE_LIMITED, Status.ROBOTS_UNAVAILABLE}:
                        break
                if problems or len(urls) > limit:
                    result.status = Status.PARTIAL
                    result.message = "; ".join(problems) or f"Returned first {limit} of {len(urls)} discovered products; pagination not followed"
        except FetchError as error:
            result = Result(self.name, "search", mpn, error.status, message=str(error))
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            result = Result(self.name, "search", mpn, Status.PARSE_ERROR, message="Supplier format not recognized: " + str(error))
        result.evidence = self.client.evidence[start:]
        return result

    def parse_product(self, document: Document, query: str | None = None) -> Offer:
        soup = BeautifulSoup(document.text, "html.parser")
        products = schema_products(soup)
        if len(products) != 1 or not string_value(products[0].get("name")):
            raise ValueError("Expected one Product JSON-LD node with a name")
        product = products[0]
        offer = Offer(self.name, document.url, document.fetched_at, product["name"])
        offer.sku = string_value(product.get("sku"))
        offer.mpn = string_value(product.get("mpn"))
        offer.candidate_mpn = title_candidate(offer.title) if not offer.mpn else None
        offer.manufacturer = string_value(product.get("brand", {}).get("name"))
        offer.manufacturer_status = "ambiguous" if offer.manufacturer and any(s in offer.manufacturer for s in [" - ", "/", ","]) else ("supplier_reported" if offer.manufacturer else "unknown")
        for field, source in [("sku", "sku"), ("mpn", "mpn"), ("manufacturer", "brand.name")]:
            if getattr(offer, field):
                offer.field_sources[field] = "Product JSON-LD " + source
        if offer.candidate_mpn:
            offer.field_sources["candidate_mpn"] = "First observed product-title token (inferred; not a verified manufacturer MPN)"
        if offer.manufacturer_status == "ambiguous":
            offer.warnings.append("Supplier manufacturer label is ambiguous")
        for row in soup.select("table tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) != 2:
                continue
            label, value = (cell.get_text(" ", strip=True) for cell in cells)
            if label.strip(": ") in {"Paket Tipi", "Kılıf / Kasa"}:
                offer.package = value
                offer.field_sources["package"] = "Visible product specification table: " + label
            if label.strip(": ") in {"Ambalaj", "Ambalaj Tipi"}:
                offer.packaging = value
                offer.field_sources["packaging"] = "Visible product specification table: " + label
        raw_offers = product.get("offers", {})
        if not isinstance(raw_offers, dict):
            raise ValueError("Expected one schema Offer object")
        offer.stock_status = stock_from_schema(raw_offers.get("availability"))
        if offer.stock_status != "unknown":
            offer.field_sources["stock_status"] = "Product JSON-LD offers.availability"
        stock_input = soup.select_one("#product-stock-status")
        if stock_input and stock_input.get("value") in {"0", "1"}:
            dom_stock = "in_stock" if stock_input["value"] == "1" else "out_of_stock"
            if offer.stock_status not in {"unknown", dom_stock}:
                offer.stock_status = "unknown"
                offer.warnings.append("Conflicting stock sources")
        qty_input = soup.select_one('input[data-qa="qty-input"]')
        if qty_input:
            offer.moq = integer_value(qty_input.get("min"), positive=True)
            offer.order_multiple = integer_value(qty_input.get("step"), positive=True)
            for field, attr in [("moq", "min"), ("order_multiple", "step")]:
                if getattr(offer, field) is not None:
                    offer.field_sources[field] = "Visible quantity input " + attr + " (UI constraint, not a contractual guarantee)"
        currency = string_value(raw_offers.get("priceCurrency"))
        for toggle, vat, label in [("price-sell-vat", "included", "KDV Dahil"), ("price-sell", "excluded", "+ KDV")]:
            price_node = soup.select_one(f'[data-toggle="{toggle}"]')
            if price_node:
                amount = decimal_value(price_node.get_text(strip=True), locale="tr")
                surrounding = " ".join(price_node.parent.parent.get_text(" ", strip=True).split()) if price_node.parent and price_node.parent.parent else ""
                explicit = label.lower() in surrounding.lower()
                if amount is not None and currency in {"TRY", "USD", "EUR", "GBP"}:
                    offer.prices.append(PriceBreak(offer.moq or 1, amount, currency, vat if explicit else "unknown", source=f"Visible [data-toggle={toggle}] and adjacent VAT label; JSON-LD currency"))
        for row in soup.select('tr[data-toggle="product-multiple"]'):
            node = row.select_one('[data-toggle="price-multiple"]')
            quantity = integer_value(row.get("data-min"))
            maximum = integer_value(row.get("data-max"))
            amount = decimal_value(node.get_text(strip=True), locale="tr") if node else None
            cells = row.find_all("td")
            price_text = cells[-1].get_text(" ", strip=True) if cells else ""
            if amount is None or quantity is None or currency not in {"TRY", "USD", "EUR", "GBP"}:
                offer.warnings.append("Unrecognized quantity-price row skipped")
                continue
            visible_currency = re.search(r"\b(TL|TRY|USD|EUR|GBP)\b", price_text)
            if not visible_currency or ("TRY" if visible_currency[1] == "TL" else visible_currency[1]) != currency:
                offer.warnings.append("Tier currency missing or inconsistent; row skipped")
                continue
            # Live LM324N variants showed data-vat=0 with the VAT-inclusive
            # base amount. This undocumented flag is not a trustworthy tax basis.
            offer.prices.append(PriceBreak(max(1, quantity), amount, currency, "unknown", maximum, source="Visible quantity table data-min/data-max/price-multiple; undocumented data-vat=" + str(row.get("data-vat"))))
        if soup.select('tr[data-toggle="product-multiple"]'):
            offer.warnings.append("Quantity-tier VAT basis unverified; undocumented data-vat flags are not treated as tax evidence")
        if not offer.prices:
            amount = decimal_value(raw_offers.get("price"))
            if amount is not None and currency in {"TRY", "USD", "EUR", "GBP"}:
                offer.prices.append(PriceBreak(offer.moq or 1, amount, currency, source="Product JSON-LD offers.price; VAT unverified"))
        offer.match = mpn_match(query, offer.mpn, offer.candidate_mpn)
        if not offer.mpn:
            offer.warnings.append("Manufacturer MPN not explicitly provided; title token cannot establish exact MPN identity")
        offer.warnings.append("Numeric stock is not disclosed by the parsed public fields")
        if not offer.prices:
            offer.warnings.append("Unit prices unavailable")
        if offer.packaging is None:
            offer.warnings.append("Shipping packaging unknown; package field describes the component case")
        if offer.moq is None or offer.order_multiple is None:
            offer.warnings.append("MOQ/order multiple unavailable")
        return offer
