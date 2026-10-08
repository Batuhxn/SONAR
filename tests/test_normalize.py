import unittest
from datetime import datetime, timezone
from decimal import Decimal

from sonar_a0.models import Offer, PriceBreak, Result, Status
from sonar_a0.normalize import decimal_value, integer_value, is_stale, mpn_match, title_candidate


class NormalizationTests(unittest.TestCase):
    def test_exact_only_full_mpn(self):
        self.assertEqual(mpn_match(" lm358p ", "LM358P"), "exact_mpn")
        for query, actual in [("LM358", "LM358P"), ("LM358P", "LM358"), ("ABC-TR", "ABC"), ("ABC/1", "ABC/2")]:
            self.assertNotEqual(mpn_match(query, actual), "exact_mpn")

    def test_missing_mpn_never_exact(self):
        self.assertEqual(mpn_match("LM358P", None, "LM358P"), "unverified_candidate")
        self.assertEqual(mpn_match("LM358P", None), "unknown")
        self.assertEqual(mpn_match("LM358", "NE555P"), "none")

    def test_title_candidate_is_observed(self):
        self.assertEqual(title_candidate("LM358P DIP-8"), "LM358P")
        self.assertIsNone(title_candidate("Example module"))
        self.assertIsNone(title_candidate("100nF capacitor"))
        self.assertIsNone(title_candidate("10kg load cell"))

    def test_decimal_locales_and_rejections(self):
        self.assertEqual(decimal_value("1.234,56", locale="tr"), Decimal("1234.56"))
        self.assertEqual(decimal_value("0.00001"), Decimal("0.00001"))
        for value in [None, "ask", "NaN", "Infinity", -1, True, ""]:
            self.assertIsNone(decimal_value(value))

    def test_integer_quantity_constraints(self):
        self.assertEqual(integer_value(0), 0)
        self.assertIsNone(integer_value(0, positive=True))
        self.assertIsNone(integer_value("1.5"))
        self.assertIsNone(integer_value(-2))

    def test_json_keeps_decimal_precision(self):
        offer = Offer("supplier", "https://example.test/p", "2026-10-08T12:00:00+00:00", "Test")
        offer.prices = [PriceBreak(1, Decimal("0.00012345"), "USD")]
        self.assertEqual(Result("supplier", "product", None, Status.OK, [offer]).to_dict()["offers"][0]["prices"][0]["unit_price"], "0.00012345")

    def test_stale_and_future_timestamps(self):
        now = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
        self.assertFalse(is_stale("2026-10-08T11:59:00+00:00", now))
        self.assertTrue(is_stale("2026-10-08T11:00:00+00:00", now))
        self.assertTrue(is_stale("2026-10-08T12:05:00+00:00", now))
        with self.assertRaises(ValueError):
            is_stale("2026-10-08T12:00:00", now)
