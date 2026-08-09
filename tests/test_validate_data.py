from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "income-statement-sankey"
SAMPLE = SKILL / "scripts/examples/aapl_q3_fy26_full.json"
CONGLOMERATE_SAMPLE = SKILL / "scripts/examples/brk_q2_2026_conglomerate.json"
NET_LOSS_SAMPLE = SKILL / "scripts/examples/intc_q2_2026_net_loss.json"
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

    def test_net_loss_sample_is_valid(self) -> None:
        net_loss_data = json.loads(NET_LOSS_SAMPLE.read_text())
        self.assertEqual(MODULE.validate(net_loss_data), [])

    def test_rejects_fabricated_net_loss_margin(self) -> None:
        net_loss_data = json.loads(NET_LOSS_SAMPLE.read_text())
        net_loss_data["net_profit"]["margin_pct"] = 67.26
        self.assertTrue(
            any(
                "net_profit.margin_pct" in error
                for error in MODULE.validate(net_loss_data)
            )
        )


class ConglomerateValidateTests(unittest.TestCase):
    """The conglomerate style drops gross profit and R&D, so its guardrails
    have to come from tying the segment footnote back to the totals."""

    def setUp(self) -> None:
        self.data = json.loads(CONGLOMERATE_SAMPLE.read_text())

    def test_sample_is_valid(self) -> None:
        self.assertEqual(MODULE.validate(self.data), [])

    def test_rejects_segment_profits_not_summing_to_operating_profit(self) -> None:
        broken = copy.deepcopy(self.data)
        broken["segments"][0]["profit"] += 1.0
        self.assertTrue(
            any(
                "segment profits -> operating profit" in error
                for error in MODULE.validate(broken)
            )
        )

    def test_rejects_fabricated_segment_margin(self) -> None:
        broken = copy.deepcopy(self.data)
        broken["segments"][0]["margin_pct"] = 90.0
        self.assertTrue(
            any("margin_pct is 90.00" in error for error in MODULE.validate(broken))
        )

    def test_rejects_fabricated_segment_yoy(self) -> None:
        broken = copy.deepcopy(self.data)
        broken["segments"][0]["yoy_pct"] = 42.0
        self.assertTrue(
            any("segments[Insurance] YoY" in error for error in MODULE.validate(broken))
        )

    def test_requires_prior_period(self) -> None:
        broken = copy.deepcopy(self.data)
        del broken["prior_period"]
        self.assertTrue(
            any("prior_period is required" in error for error in MODULE.validate(broken))
        )

    def test_rejects_missing_segment_profit(self) -> None:
        broken = copy.deepcopy(self.data)
        del broken["segments"][0]["profit"]
        self.assertTrue(
            any(
                "every segment requires a profit figure" in error
                for error in MODULE.validate(broken)
            )
        )

    def test_rejects_spoofed_official_url(self) -> None:
        broken = copy.deepcopy(self.data)
        broken["source_records"][0]["url"] = "https://stockanalysis.com/brk.pdf"
        self.assertTrue(
            any("not acceptable" in error for error in MODULE.validate(broken))
        )

    def test_rejects_unbalanced_pretax(self) -> None:
        broken = copy.deepcopy(self.data)
        broken["tax"] += 1.0
        self.assertTrue(
            any(
                "net profit + tax -> pre-tax profit" in error
                for error in MODULE.validate(broken)
            )
        )


if __name__ == "__main__":
    unittest.main()
