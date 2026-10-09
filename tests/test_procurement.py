import csv
import io
import unittest

from sonar_web.bom import Component, validate
from sonar_web.procurement import csv_safe, export_csv, line, procurement


def part(prices=None, **offer_fields):
    c = Component('c1', 'Amplifier', 'TEST1', '2', 'U1 U2', raw={'Unknown': 'keep'})
    validate([c], 5)
    offer = {'supplier': 'direnc', 'title': 'Test product', 'url': 'https://www.direnc.net/test', 'match': 'exact_mpn',
             'stock_status': 'in_stock', 'stock_quantity': 100, 'fetched_at': '2026-10-09T10:00:00+00:00', 'moq': 1,
             'order_multiple': 1, 'prices': prices if prices is not None else [{'min_quantity': 1, 'unit_price': '1.25', 'currency': 'TRY', 'vat': 'included'}],
             'warnings': [], **offer_fields}
    c.results = {'direnc': {'offers': [offer]}}
    c.choice = {'supplier': 'direnc', 'offer': 0, 'tier': 0 if offer['prices'] else -1}
    return c


class ProcurementTests(unittest.TestCase):
    def test_decimal_cost_and_board_count(self):
        result = line(part(), 'BoM', 5)
        self.assertEqual(result['required'], 10)
        self.assertEqual(result['known_cost'], '12.50')
        self.assertEqual(result['pcbs'], 5)

    def test_moq_multiple_and_price_tier(self):
        c = part([{'min_quantity': 15, 'unit_price': '1', 'currency': 'USD', 'vat': 'unknown'}], moq=12, order_multiple=4)
        result = line(c, 'BoM')
        self.assertEqual(result['order_quantity'], 16)
        self.assertEqual(result['known_cost'], '16')
        self.assertTrue(any('increased' in w for w in result['warnings']))

    def test_price_max_not_used_outside_range(self):
        c = part([{'min_quantity': 1, 'max_quantity': 5, 'unit_price': '1', 'currency': 'TRY', 'vat': 'included'}])
        self.assertIsNone(line(c, 'BoM')['known_cost'])

    def test_no_price_is_unknown_not_zero(self):
        c = part([])
        result = line(c, 'BoM')
        self.assertIsNone(result['unit_price'])
        self.assertIsNone(result['known_cost'])
        self.assertEqual(result['order_quantity'], 10)

    def test_zero_stock_and_unknown_distinct(self):
        zero = line(part(stock_quantity=0, stock_status='out_of_stock'), 'BoM')
        unknown = line(part(stock_quantity=None, stock_status='unknown'), 'BoM')
        self.assertEqual(zero['stock_quantity'], 0)
        self.assertIsNone(unknown['stock_quantity'])
        self.assertTrue(any('insufficient' in w for w in zero['warnings']))

    def test_ambiguous_match_remains_visible(self):
        result = line(part(match='candidate_mpn'), 'BoM')
        self.assertEqual(result['match'], 'candidate_mpn')
        self.assertTrue(any('Unverified' in w for w in result['warnings']))

    def test_invalid_quantity_prevents_cost(self):
        c = part(); c.quantity = 'bad'; validate([c], 1)
        self.assertIsNone(line(c, 'BoM')['known_cost'])

    def test_currency_and_vat_totals_separate(self):
        parts = [part(), part([{'min_quantity': 1, 'unit_price': '2', 'currency': 'USD', 'vat': 'unknown'}]), part([{'min_quantity': 1, 'unit_price': '2', 'currency': 'TRY', 'vat': 'excluded'}]), part([])]
        report = procurement({'b': {'name': 'BoM', 'boards': 5, 'components': parts}})
        self.assertEqual(len(report['totals']), 3)
        self.assertEqual(report['missing_costs'], 1)

    def test_dnp_and_unselected_excluded(self):
        a, b = part(), part(); a.dnp = True; b.selected = False
        self.assertEqual(procurement({'b': {'name': 'BoM', 'boards': 1, 'components': [a, b]}})['lines'], [])

    def test_csv_correctness_and_formula_protection(self):
        c = part(); c.name = '=HYPERLINK("evil")'
        result = line(c, 'Test, BoM', 5)
        content = export_csv([result])
        rows = list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
        self.assertEqual(rows[0]['bom'], 'Test, BoM')
        self.assertEqual(rows[0]['name'], "'" + c.name)
        self.assertEqual(rows[0]['pcbs'], '5')
        self.assertEqual(rows[0]['known_cost'], '12.50')
        self.assertIn('keep', rows[0]['source_fields'])
        for value in ['=x', '+x', '-x', '@x', '  =x', '\tx']:
            self.assertTrue(csv_safe(value).startswith("'"))


if __name__ == '__main__':
    unittest.main()
