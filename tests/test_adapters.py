import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

from sonar_a0.adapters import DirencAdapter, OzdisanAdapter, SupplierAdapter
from sonar_a0.models import Status
from sonar_a0.transport import Document, FetchError

FIXTURES = Path(__file__).parent / "fixtures"
STAMP = "2026-10-08T12:00:00+00:00"


def document(name, supplier="direnc"):
    host = "www.direnc.net" if supplier == "direnc" else "www.ozdisan.com"
    return Document(f"https://{host}/test-product", (FIXTURES / name).read_text(encoding="utf-8"), STAMP, "fixture-not-live")


class AdapterTests(unittest.TestCase):
    def test_adapters_share_contract(self):
        self.assertIsInstance(DirencAdapter(), SupplierAdapter)
        self.assertIsInstance(OzdisanAdapter(), SupplierAdapter)

    def test_ozdisan_normalization_and_packaging(self):
        offer = OzdisanAdapter().parse_product(document("ozdisan.html", "ozdisan"), "TEST123-TR")
        self.assertEqual(offer.mpn, "TEST123-TR")
        self.assertEqual(offer.sku, "SKU-123")
        self.assertEqual(offer.match, "exact_mpn")
        self.assertEqual(offer.stock_quantity, 1234)
        self.assertEqual(offer.moq, 5)
        self.assertEqual(offer.order_multiple, 5)
        self.assertEqual(offer.mpq, 2500)
        self.assertEqual(offer.package, "SOIC8")
        self.assertEqual({p.currency for p in offer.prices}, {"TRY", "USD", "EUR"})
        self.assertEqual({p.packaging for p in offer.prices}, {"CUT TAPE", "TAPE&REEL"})
        self.assertTrue(all(p.vat == "unknown" for p in offer.prices))
        self.assertEqual(offer.fetched_at, STAMP)

    def test_ozdisan_hidden_stock_and_price(self):
        doc = document("ozdisan.html", "ozdisan")
        doc.text = doc.text.replace('"isShowStock":true', '"isShowStock":false').replace('"isShowPrice":true', '"isShowPrice":false')
        offer = OzdisanAdapter().parse_product(doc)
        self.assertEqual(offer.stock_status, "not_disclosed")
        self.assertIsNone(offer.stock_quantity)
        self.assertEqual(offer.prices, [])

    def test_ozdisan_out_of_stock_distinct_from_unknown(self):
        doc = document("ozdisan.html", "ozdisan")
        doc.text = doc.text.replace('"totalStock":1234', '"totalStock":0').replace('https://schema.org/InStock','https://schema.org/OutOfStock')
        offer = OzdisanAdapter().parse_product(doc)
        self.assertEqual(offer.stock_status, "out_of_stock")
        self.assertEqual(offer.stock_quantity, 0)

    def test_ozdisan_conflicting_stock_suppressed(self):
        doc = document("ozdisan.html", "ozdisan")
        doc.text = doc.text.replace('https://schema.org/InStock','https://schema.org/OutOfStock')
        offer = OzdisanAdapter().parse_product(doc)
        self.assertEqual(offer.stock_status, "unknown")
        self.assertIsNone(offer.stock_quantity)

    def test_direnc_unknown_identity_and_stock_count(self):
        offer = DirencAdapter().parse_product(document("direnc.html"), "TEST456P")
        self.assertIsNone(offer.mpn)
        self.assertEqual(offer.candidate_mpn, "TEST456P")
        self.assertEqual(offer.match, "unverified_candidate")
        self.assertEqual(offer.manufacturer_status, "ambiguous")
        self.assertEqual(offer.stock_status, "in_stock")
        self.assertIsNone(offer.stock_quantity)
        self.assertEqual((offer.moq, offer.order_multiple), (5, 5))
        self.assertEqual(offer.package, "DIP8/7.62mm")
        self.assertIsNone(offer.packaging)

    def test_direnc_vat_and_quantity_breaks(self):
        offer = DirencAdapter().parse_product(document("direnc.html"))
        self.assertIn((Decimal("10.42"), "excluded"), {(p.unit_price,p.vat) for p in offer.prices})
        self.assertIn((Decimal("12.50"), "included"), {(p.unit_price,p.vat) for p in offer.prices})
        tier = next(p for p in offer.prices if p.min_quantity == 10)
        self.assertEqual((tier.unit_price, tier.max_quantity, tier.currency), (Decimal("11.50"),99,"TRY"))
        self.assertGreaterEqual(min(p.min_quantity for p in offer.prices), 1)

    def test_direnc_explicit_mpn_and_currency(self):
        doc = document("direnc.html")
        doc.text = doc.text.replace('"sku":"T456"', '"sku":"T456","mpn":"TEST456P"').replace('"TRY"','"EUR"').replace(' TL',' EUR')
        offer = DirencAdapter().parse_product(doc, "TEST456P")
        self.assertEqual(offer.match, "exact_mpn")
        self.assertTrue(all(p.currency == "EUR" for p in offer.prices))

    def test_undocumented_tier_vat_never_asserted(self):
        doc=document("direnc.html")
        doc.text=doc.text.replace('data-vat="1"','data-vat="0"')
        offer=DirencAdapter().parse_product(doc)
        self.assertTrue(all(p.vat=="unknown" for p in offer.prices if p.max_quantity is not None))

    def test_direnc_missing_stock_and_price(self):
        doc = Document("https://www.direnc.net/test", '<script type="application/ld+json">{"@type":"Product","name":"TEST100","offers":{}}</script>', STAMP, "synthetic")
        offer = DirencAdapter().parse_product(doc)
        self.assertEqual(offer.prices, [])
        self.assertIsNone(offer.stock_quantity)
        self.assertEqual(offer.stock_status, "unknown")

    def test_direnc_conflicting_stock(self):
        doc = document("direnc.html")
        doc.text = doc.text.replace('id="product-stock-status" value="1"','id="product-stock-status" value="0"')
        self.assertEqual(DirencAdapter().parse_product(doc).stock_status,"unknown")

    def test_product_unexpected_format_is_parse_error(self):
        client = Mock(evidence=[])
        client.get.return_value = Document("https://www.direnc.net/test", "<html>changed</html>", STAMP, "synthetic")
        for adapter in [DirencAdapter(client), OzdisanAdapter(client)]:
            self.assertEqual(adapter.product("https://www.direnc.net/test").status, Status.PARSE_ERROR)

    def test_product_request_failure_propagates(self):
        client = Mock(evidence=[])
        for status in [Status.TIMEOUT,Status.BLOCKED,Status.NOT_FOUND,Status.RATE_LIMITED,Status.NETWORK_ERROR]:
            client.get.side_effect = FetchError(status, "fixture failure")
            self.assertEqual(DirencAdapter(client).product("https://www.direnc.net/test").status,status)

    def test_search_discovers_supplier_links(self):
        client = Mock(evidence=[])
        client.get.side_effect = [document("direnc-search.html"),document("direnc.html")]
        result = DirencAdapter(client).search("TEST456P")
        self.assertEqual(len(result.offers), 1)
        self.assertEqual(client.get.call_args_list[1].args[0],"https://www.direnc.net/test-product")
        self.assertEqual(result.offers[0].match, "unverified_candidate")

    def test_search_explicit_empty_vs_changed(self):
        client = Mock(evidence=[])
        adapter = DirencAdapter(client)
        for content,expected in [("ilgili ürün bulunamadı",Status.NOT_FOUND),("unrecognized page",Status.PARSE_ERROR)]:
            client.get.return_value = Document("https://www.direnc.net/arama?q=TEST",content,STAMP,"synthetic")
            self.assertEqual(adapter.search("TEST").status,expected)

    def test_ozdisan_search_does_not_mask_robots_block(self):
        client = Mock(evidence=[])
        client.get.side_effect = FetchError(Status.ROBOTS_DISALLOWED,"disallowed")
        result = OzdisanAdapter(client).search("LM358P")
        self.assertEqual(result.status,Status.ROBOTS_DISALLOWED)
        self.assertEqual(result.offers,[])

    def test_limits_rejected(self):
        for adapter in [DirencAdapter(),OzdisanAdapter()]:
            with self.assertRaises(ValueError): adapter.search("",limit=1)
            with self.assertRaises(ValueError): adapter.search("TEST",limit=0)
