from __future__ import annotations

import json
from decimal import Decimal
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from ..models import Offer, PriceBreak, Result, Status
from ..normalize import decimal_value, integer_value, mpn_match, schema_products, stock_from_schema, string_value
from ..transport import Document, FetchError
from .base import SupplierAdapter


class OzdisanAdapter(SupplierAdapter):
    name = "ozdisan"
    hosts = {"www.ozdisan.com", "ozdisan.com"}

    def search(self, mpn: str, *, limit: int = 5) -> Result:
        if not mpn.strip() or not 1 <= limit <= 20:
            raise ValueError("A nonempty query and limit 1..20 are required")
        url = "https://www.ozdisan.com/c?" + urlencode({"search": mpn})
        start = len(self.client.evidence)
        try:
            self.client.get(url)
            # Search is currently disallowed. A changed policy does not automatically
            # validate a new discovery parser: fail explicitly until investigated.
            result = Result(self.name, "search", mpn, Status.PARTIAL, message="Search response accessible, but discovery parser is not validated; product(url) is available")
        except FetchError as error:
            result = Result(self.name, "search", mpn, error.status, message=str(error))
        result.evidence = self.client.evidence[start:]
        return result

    def parse_product(self, document: Document, query: str | None = None) -> Offer:
        soup = BeautifulSoup(document.text, "html.parser")
        products = schema_products(soup)
        if len(products) != 1 or not string_value(products[0].get("name")):
            raise ValueError("Expected one Product JSON-LD node with a name")
        product = products[0]
        offer = Offer(self.name, document.url, document.fetched_at, product["name"])
        offer.mpn = string_value(product.get("mpn"))
        offer.sku = string_value(product.get("sku"))
        offer.manufacturer = string_value(product.get("brand", {}).get("name"))
        offer.manufacturer_status = "supplier_reported" if offer.manufacturer else "unknown"
        for field in ["mpn", "sku", "manufacturer"]:
            if getattr(offer, field):
                offer.field_sources[field] = "Product JSON-LD: " + ("brand.name" if field == "manufacturer" else field)
        for prop in product.get("additionalProperty", []):
            if prop.get("name") in {"Kılıf / Kasa", "Package / Case"}:
                offer.package = string_value(prop.get("value"))
                offer.field_sources["package"] = "Product JSON-LD additionalProperty"
        nxt = soup.find("script", id="__NEXT_DATA__")
        props = json.loads(nxt.get_text(), parse_float=Decimal)["props"]["pageProps"] if nxt else {}
        data = props.get("data", {})
        availability = data.get("availability", {})
        offer.packaging = string_value(data.get("variantPackageType"))
        if offer.packaging:
            offer.field_sources["packaging"] = "pageProps.data.variantPackageType"
        for field, key in [("moq", "minimumOrderQuantity"), ("order_multiple", "orderQuantityMultiplier"), ("mpq", "mpq")]:
            value = integer_value(availability.get(key), positive=True)
            setattr(offer, field, value)
            if value is not None:
                offer.field_sources[field] = "pageProps.data.availability." + key
        if availability.get("isShowStock") is False:
            offer.stock_status = "not_disclosed"
        elif availability.get("isShowStock") is True:
            offer.stock_quantity = integer_value(availability.get("totalStock"))
            if offer.stock_quantity is not None:
                offer.stock_status = "in_stock" if offer.stock_quantity > 0 else "out_of_stock"
                offer.field_sources["stock_quantity"] = "pageProps.data.availability.totalStock"
        schema_offers = product.get("offers", [])
        schema_offers = [schema_offers] if isinstance(schema_offers, dict) else schema_offers
        if len(schema_offers) == 1:
            schema_stock = stock_from_schema(schema_offers[0].get("availability"))
            if offer.stock_status == "unknown":
                offer.stock_status = schema_stock
                offer.field_sources["stock_status"] = "Product JSON-LD offers.availability"
            elif schema_stock not in {"unknown", offer.stock_status} and offer.stock_status != "not_disclosed":
                offer.stock_status, offer.stock_quantity = "unknown", None
                offer.warnings.append("Conflicting stock sources; quantity suppressed")
        response = props.get("initialPrice", {}).get("response", {})
        if availability.get("isShowPrice") is False:
            offer.warnings.append("Supplier does not disclose price on this public page")
        elif response.get("success") is True:
            for package in response.get("data", {}).get("packages", []):
                packaging = string_value(package.get("packaging"))
                for tier in package.get("priceBreaks", []):
                    quantity = integer_value(tier.get("breakQuantity"), positive=True)
                    for price in tier.get("prices", []):
                        amount = decimal_value(price.get("price"))
                        currency = string_value(price.get("currency"))
                        if quantity is not None and amount is not None and currency in {"TRY", "USD", "EUR", "GBP"}:
                            offer.prices.append(PriceBreak(quantity, amount, currency, packaging=packaging, source="pageProps.initialPrice.response.data.packages[].priceBreaks[].prices[].price"))
        elif not nxt:
            # Public schema data is a fallback, but packaging/MOQ/quantity may be unknown.
            for item in schema_offers:
                for tier in item.get("priceSpecification", []):
                    quantity = integer_value(tier.get("eligibleQuantity", {}).get("minValue"), positive=True)
                    amount = decimal_value(tier.get("price"))
                    currency = string_value(tier.get("priceCurrency"))
                    if quantity is not None and amount is not None and currency in {"TRY", "USD", "EUR", "GBP"}:
                        offer.prices.append(PriceBreak(quantity, amount, currency, source="Product JSON-LD offers.priceSpecification"))
        offer.match = mpn_match(query, offer.mpn)
        if not offer.mpn:
            offer.warnings.append("Manufacturer MPN unavailable; no exact match asserted")
        if not offer.prices:
            offer.warnings.append("Unit prices unavailable")
        else:
            offer.warnings.append("Unit-price VAT basis unverified; do not compare to VAT-inclusive prices")
        if offer.stock_quantity is None:
            offer.warnings.append("Numeric stock unavailable")
        if offer.moq is None or offer.order_multiple is None:
            offer.warnings.append("MOQ/order multiple unavailable")
        return offer
