import io
import unittest
import zipfile
from pathlib import Path

from openpyxl import Workbook

from sonar_web.bom import Component, import_components, parse_dnp, parse_quantity, read_table, recognize, references, validate

EXAMPLES = Path(__file__).parents[1] / "examples"


def workbook_bytes(rows, extra_sheet=False):
    wb = Workbook()
    wb.active.title = "BoM"
    for row in rows:
        wb.active.append(row)
    if extra_sheet:
        wb.create_sheet("Other").append(["Reference", "MPN"])
        wb["Other"].append(["U9", "TEST9"])
    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()


def load_example(name):
    table = read_table((EXAMPLES / name).read_bytes(), name)
    return import_components(table, table["mapping"])


class BomTests(unittest.TestCase):
    def test_altium_csv(self):
        parts = load_example("altium_a1.csv")
        self.assertEqual(len(parts), 4)
        self.assertEqual(parts[0].mpn, "LM358P")
        self.assertEqual(parts[0].quantity, "2")
        self.assertTrue(parts[2].dnp)
        self.assertIn("6: Footprint", parts[0].raw)
        self.assertFalse(parts[0].issues)

    def test_kicad_tsv(self):
        parts = load_example("kicad_a1.tsv")
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[1].references, "R1 R2")
        self.assertTrue(parts[2].dnp)

    def test_kicad_csv_and_utf8_bom(self):
        table = read_table(b'\xef\xbb\xbfReference,Value,MPN,Qty\nU1,Amplifier, lm358p ,1\n', "kicad.csv")
        self.assertEqual(import_components(table, table["mapping"])[0].mpn, "LM358P")

    def test_altium_xlsx_and_sheet_choice(self):
        data = workbook_bytes([["Engineering report"], ["Designator", "Comment", "Manufacturer Part Number", "Quantity", "Fitted"], ["U1", "Amplifier", "LM358P", 1, "Yes"]], True)
        table = read_table(data, "altium.xlsx")
        self.assertEqual(table["header_row"], 2)
        self.assertEqual(table["preamble"], [["Engineering report"]])
        self.assertFalse(import_components(table, table["mapping"])[0].dnp)
        other = read_table(data, "altium.xlsx", "Other")
        self.assertEqual(import_components(other, other["mapping"])[0].quantity, "1")

    def test_manual_column_mapping(self):
        table = read_table(b'custom1,custom2,custom3,custom4,other\nAmplifier,part-1/tr,2,"U1,U2",keep-me\n', "custom.csv")
        parts = import_components(table, {"name": 0, "mpn": 1, "quantity": 2, "references": 3})
        self.assertEqual(parts[0].mpn, "PART-1/TR")
        self.assertEqual(parts[0].raw["5: other"], "keep-me")

    def test_quantity_calculation_and_dnp(self):
        parts = load_example("altium_a1.csv")
        validate(parts, 25)
        self.assertEqual(parts[0].required, 50)
        self.assertEqual(parts[1].required, 75)
        self.assertEqual(parts[2].required, 0)

    def test_quantity_validation(self):
        for value in ["", "NaN", "Infinity", "-1", "0", "1.2", "1,000", "=2+3", "1000001"]:
            self.assertIsNone(parse_quantity(value), value)
        for value in ["2", "2.0", "2e0"]:
            self.assertEqual(parse_quantity(value), 2)

    def test_dnp_and_fitted_values(self):
        self.assertTrue(parse_dnp("Do Not Populate"))
        self.assertFalse(parse_dnp(""))
        self.assertIsNone(parse_dnp("maybe"))
        self.assertFalse(parse_dnp("Fitted", True))
        self.assertFalse(parse_dnp("yes", True))
        self.assertTrue(parse_dnp("No", True))
        self.assertTrue(parse_dnp("DNP", True))
        self.assertIsNone(parse_dnp("", True))

    def test_unknown_dnp_not_silently_populated(self):
        table = read_table(b'Reference,MPN,Qty,DNP\nU1,P1,1,maybe\n', "bom.csv")
        c = import_components(table, table["mapping"])[0]
        self.assertIsNone(c.dnp)
        self.assertIsNone(c.required)
        self.assertTrue(any("DNP" in i for i in c.issues))

    def test_reference_ranges(self):
        self.assertEqual(references("R1-R3; C1 C2"), ["R1", "R2", "R3", "C1", "C2"])
        self.assertEqual(references("R3-R1"), ["R3-R1"])

    def test_safe_duplicate_identification(self):
        table = read_table(b'Reference,MPN,Qty\nU1,P1,1\nU1,P1,1\nU2,P1,1\n', "bom.csv")
        parts = import_components(table, table["mapping"])
        self.assertEqual(len(parts), 3)
        self.assertTrue(any("duplicate row" in i for i in parts[0].issues))
        self.assertTrue(any("Duplicate reference" in i for i in parts[1].issues))
        self.assertFalse(any("duplicate" in i.lower() for i in parts[2].issues))

    def test_malformed_rows_and_extra_columns_preserved(self):
        table = read_table(b'Reference,MPN,Qty\nU1,P1,bad,extra\nmissing-only\n', "bom.csv")
        parts = import_components(table, table["mapping"])
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0].raw["4: Extra column 4"], "extra")
        self.assertIsNone(parts[0].required)
        self.assertIsNone(parts[1].required)

    def test_duplicate_column_names_preserved(self):
        table = read_table(b'MPN,MPN,Reference,Qty\nP1,P2,U1,1\n', "bom.csv")
        c = import_components(table, table["mapping"])[0]
        self.assertEqual(c.raw["1: MPN"], "P1")
        self.assertEqual(c.raw["2: MPN"], "P2")

    def test_formulas_preserved_not_evaluated(self):
        table = read_table(workbook_bytes([["Reference", "MPN", "Qty", "Custom"], ["U1", "P1", "=1+1", "=HYPERLINK(\"https://example.org\")"]]), "bom.xlsx")
        c = import_components(table, table["mapping"])[0]
        self.assertEqual(c.quantity, "=1+1")
        self.assertIsNone(c.required)
        self.assertTrue(any("formula" in i for i in c.issues))

    def test_mapping_validation(self):
        table = read_table(b'MPN,Qty\nP1,1\n', "bom.csv")
        for mapping in [{"mpn": 10}, {"name": 0, "mpn": 0}, {"bad": 0}, {"quantity": 1}, {"mpn": True}]:
            with self.assertRaises(ValueError):
                import_components(table, mapping)

    def test_board_validation(self):
        for boards in [0, -1, 1.5, True, 100001]:
            with self.assertRaises(ValueError):
                validate([], boards)

    def test_empty_binary_and_bad_files(self):
        for data, name in [(b'', 'a.csv'), (b'abc\x00', 'a.csv'), (b'not a zip', 'a.xlsx'), (b'anything', 'a.exe'), (b'MPN,Qty\n', 'a.csv')]:
            with self.assertRaises(ValueError):
                read_table(data, name)

    def test_limits_and_zip_expansion(self):
        with self.assertRaises(ValueError):
            read_table(('MPN,Qty\n' + 'P1,1\n' * 5001).encode(), 'large.csv')
        with self.assertRaises(ValueError):
            read_table(('MPN,Qty\n' + 'P' * 2001 + ',1\n').encode(), 'wide.csv')
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('bomb.xml', b'x' * 30_000_001)
        with self.assertRaisesRegex(ValueError, 'Expanded workbook'):
            read_table(stream.getvalue(), 'bomb.xlsx')

    def test_unknown_sheet(self):
        with self.assertRaisesRegex(ValueError, 'Worksheet'):
            read_table(workbook_bytes([["MPN"], ["P1"]]), "bom.xlsx", "Missing")

    def test_aliases(self):
        self.assertEqual(recognize(["Manufacturer Part Number", "Designators", "Count", "Do Not Populate"]), {"mpn": 0, "quantity": 2, "references": 1, "dnp": 3})

    def test_source_whitespace_preserved(self):
        table = read_table(b'Reference,MPN,Qty,Unknown\nU1, P1 ,1,  keep this  \n', 'source.csv')
        c = import_components(table, table['mapping'])[0]
        self.assertEqual(c.mpn, 'P1')
        self.assertEqual(c.raw['4: Unknown'], '  keep this  ')

    def test_reference_expansion_is_bounded(self):
        result = references('R1-R5000 R5001-R10000')
        self.assertLessEqual(len(result), 5001)
        self.assertIn('R5001-R10000', result)

    def test_committed_altium_workbook(self):
        parts = load_example('altium_a1.xlsx')
        self.assertEqual(len(parts), 4)
        self.assertEqual(parts[0].mpn, 'LM358P')


if __name__ == '__main__':
    unittest.main()
