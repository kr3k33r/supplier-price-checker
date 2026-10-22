import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reconciliation import analyze, safe_csv


def file(text, name="one.csv"):
    return {"name": name, "text": "Артикул;Название;Цена;Остаток\n" + text}


class ReconciliationTests(unittest.TestCase):
    def test_identifiers_and_decimal_and_inventory(self):
        report = analyze([file("001;Гайка;12,50;2\n"), file("001;Гайка;10;0\n", "two.csv")])
        self.assertEqual(report["products"][0]["sku"], "001")
        self.assertEqual(report["products"][0]["min_price"], "12.50")
        self.assertTrue(report["summary"]["balance_ok"])

    def test_duplicate_conflict_and_invalid_are_accounted_for(self):
        report = analyze([file("01;А;10;1\n01;А;10;1\n02;Б;20;1\n02;Б;30;1\n03;В;NaN;1\n")])
        self.assertEqual(
            report["summary"],
            {
                "input_rows": 5,
                "valid_rows": 1,
                "excluded_rows": 1,
                "duplicates": 1,
                "conflict_rows": 2,
                "products": 1,
                "balance_ok": True,
            },
        )

    def test_price_precision_and_negative(self):
        report = analyze([file("1;А;1.001;1\n2;Б;-1;2\n3;В;10;0.5\n")])
        self.assertEqual(report["summary"]["excluded_rows"], 3)

    def test_aliases_bom_and_commas(self):
        report = analyze([{"name": "a.csv", "text": "\ufeffSKU,Name,Price,Stock\n001,A,3.50,1\n"}])
        self.assertEqual(report["summary"]["products"], 1)

    def test_conflict_names_flagged_without_guessing(self):
        report = analyze([file("1;Один;10;2\n"), file("1;Другой;10;2\n", "b.csv")])
        self.assertTrue(report["products"][0]["review"])

    def test_duplicate_headers_rejected(self):
        with self.assertRaises(ValueError):
            analyze([{"name": "a", "text": "sku;sku;name;price;stock\n1;1;a;2;3\n"}])

    def test_formula_injection_neutralized(self):
        self.assertIn("'  =1+1", safe_csv([{"a": "  =1+1"}], ["a"]))

    def test_extra_fields_excluded(self):
        self.assertEqual(analyze([file("1;А;10;2;лишнее\n")])["summary"]["excluded_rows"], 1)


if __name__ == "__main__":
    unittest.main()
