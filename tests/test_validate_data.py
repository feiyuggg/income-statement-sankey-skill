from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "income-statement-sankey"
SAMPLE = SKILL / "scripts/examples/aapl_q3_fy26_full.json"
SPEC = importlib.util.spec_from_file_location(
    "validate_data", SKILL / "scripts/validate_data.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ValidateDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = json.loads(SAMPLE.read_text())

    def test_official_sample_is_valid(self) -> None:
        self.assertEqual(MODULE.validate(self.data), [])

    def test_rejects_spoofed_official_url(self) -> None:
        broken = copy.deepcopy(self.data)
        broken["source_records"][0]["url"] = "https://example.invalid/report.pdf"
        self.assertTrue(
            any("not acceptable" in error for error in MODULE.validate(broken))
        )

    def test_rejects_missing_revenue_composition(self) -> None:
        broken = copy.deepcopy(self.data)
        broken["revenue_groups"] = []
        self.assertTrue(
            any("at least two" in error for error in MODULE.validate(broken))
        )

    def test_rejects_material_reconciliation_error(self) -> None:
        broken = copy.deepcopy(self.data)
        broken["gross_profit"]["amount"] += 0.5
        self.assertTrue(
            any("gross profit + COGS" in error for error in MODULE.validate(broken))
        )

    def test_rejects_fabricated_yoy(self) -> None:
        broken = copy.deepcopy(self.data)
        broken["total_revenue"]["yoy_pct"] = 999
        self.assertTrue(
            any("total_revenue YoY" in error for error in MODULE.validate(broken))
        )


if __name__ == "__main__":
    unittest.main()
