import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reconciliation import analyze, inspect, merge, number, safe_csv
from table_io import read_files


class MappingTests(unittest.TestCase):
    def test_custom_headers_and_optional_stock(self):
        source = {
            "name": "a.csv",
            "text": "Номенклатура|Текст|Розница\n0001|Фильтр|12,50\n",
            "delimiter": "|",
            "mapping": {"sku": "Номенклатура", "name": "Текст", "price": "Розница", "stock": ""},
        }
        report = analyze([source])
        self.assertEqual(report["products"][0]["sku"], "0001")
        self.assertIsNone(report["products"][0]["available"])
        self.assertEqual(report["products"][0]["min_price"], "12.50")

    def test_header_row_and_provenance(self):
        source = {
            "name": "a.csv",
            "text": "Отчёт поставщика\nКод;Товар;Цена\n01;Гайка;15\n",
            "header_row": 2,
        }
        self.assertEqual(analyze([source])["rows"][0]["line"], 3)

    def test_missing_mapping_rejected(self):
        with self.assertRaises(ValueError):
            analyze([{"name": "a", "text": "x;y\n1;2\n", "mapping": {"sku": "x"}}])

    def test_mapping_same_source_twice_rejected(self):
        with self.assertRaises(ValueError):
            analyze(
                [
                    {
                        "name": "a",
                        "text": "x;y;z\n1;2;3\n",
                        "mapping": {"sku": "x", "name": "x", "price": "z"},
                    }
                ]
            )

    def test_general_union_preserves_optional_blanks(self):
        fields = [
            {"name": "Код", "required": True},
            {"name": "Сумма", "type": "number"},
            {"name": "Город"},
        ]
        sources = [
            {
                "name": "one",
                "text": "id;total\n001;12,50\n",
                "mapping": {"Код": "id", "Сумма": "total"},
            },
            {
                "name": "two",
                "text": "номер;город\n002;Омск\n",
                "mapping": {"Код": "номер", "Город": "город"},
            },
        ]
        report = merge(sources, fields)
        self.assertEqual(report["rows"][0]["values"], {"Код": "001", "Сумма": "12.50", "Город": ""})
        self.assertEqual(report["rows"][1]["values"]["Город"], "Омск")
        self.assertTrue(report["summary"]["balance_ok"])

    def test_general_types_missing_required_and_dedup(self):
        source = {
            "name": "a",
            "text": "id;qty\n001;2\n001;2\n002;1.5\n;3\n",
            "mapping": {"Код": "id", "Штук": "qty"},
        }
        report = merge(
            [source], [{"name": "Код", "required": True}, {"name": "Штук", "type": "integer"}], True
        )
        self.assertEqual(report["summary"]["valid_rows"], 1)
        self.assertEqual(report["summary"]["duplicates"], 1)
        self.assertEqual(report["summary"]["excluded_rows"], 2)

    def test_union_keeps_duplicates_by_default(self):
        report = merge([{"name": "a", "text": "id\n001\n001\n"}], [{"name": "id"}])
        self.assertEqual(report["summary"]["valid_rows"], 2)

    def test_custom_schema_rejects_duplicate_and_reserved_names(self):
        for fields in [
            [{"name": "A"}, {"name": "a"}],
            [{"name": "__source"}],
            [{"name": "x", "type": "unknown"}],
        ]:
            with self.assertRaises(ValueError):
                merge([{"name": "a", "text": "id\n001\n"}], fields)

    def test_preview_and_auto_mapping(self):
        report = inspect([{"name": "a", "text": "SKU;Name;Price\n01;Фильтр;5\n"}])
        self.assertEqual(report["files"][0]["suggestions"]["sku"], "SKU")
        self.assertIsNone(report["files"][0]["suggestions"]["stock"])
        self.assertEqual(len(report["files"][0]["preview"]), 1)

    def test_extreme_decimal_is_validation_error(self):
        with self.assertRaises(ValueError):
            number("1e999999999")

    def test_export_protects_header_and_empty_cell(self):
        output = safe_csv([{"=formula": None}], ["=formula"])
        self.assertIn("'=formula", output)
        self.assertNotIn("None", output)

    def test_bad_header_row_and_delimiter(self):
        for update in [
            {"header_row": True},
            {"header_row": 0},
            {"header_row": 21},
            {"delimiter": ":"},
        ]:
            with self.assertRaises(ValueError):
                read_files([{"name": "a", "text": "id\n1\n", **update}])
