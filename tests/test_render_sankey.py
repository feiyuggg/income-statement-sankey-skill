from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "income-statement-sankey/scripts/render_sankey.py"
SPEC = importlib.util.spec_from_file_location("render_sankey", RENDERER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BoundedStackedSpansTests(unittest.TestCase):
    def test_preserves_requested_heights_inside_parent(self) -> None:
        self.assertEqual(
            MODULE._bounded_stacked_spans(10.0, 30.0, [4.0, 6.0]),
            [(10.0, 14.0), (14.0, 20.0)],
        )

    def test_scales_overflow_to_parent_bottom(self) -> None:
        spans = MODULE._bounded_stacked_spans(10.0, 30.0, [12.0, 18.0])
        self.assertAlmostEqual(spans[0][0], 10.0)
        self.assertAlmostEqual(spans[0][1], 18.0)
        self.assertAlmostEqual(spans[1][0], 18.0)
        self.assertAlmostEqual(spans[1][1], 30.0)


class RightProfitLayoutTests(unittest.TestCase):
    def test_stacks_large_net_profit_and_tax_without_overlap(self) -> None:
        layout = MODULE._right_profit_layout(
            net_height=299.0,
            tax_height=71.0,
            operating_bottom=474.0,
            opex_top=590.0,
            opex_bottom=678.0,
            other_height=261.0,
            other_bar_width=55.0,
            net_is_loss=False,
            other_inflow=True,
        )

        self.assertAlmostEqual(layout["net_top"], 250.0)
        self.assertAlmostEqual(layout["tax_top"], 569.0)
        self.assertLessEqual(layout["tax_top"] + 71.0, 640.0)
        self.assertGreaterEqual(layout["expense_start"], 700.0)

    def test_uses_open_gap_for_operating_expense_label(self) -> None:
        layout = MODULE._right_profit_layout(
            net_height=299.0,
            tax_height=71.0,
            operating_bottom=474.0,
            opex_top=590.0,
            opex_bottom=678.0,
            other_height=261.0,
            other_bar_width=55.0,
            net_is_loss=False,
            other_inflow=True,
        )

        self.assertTrue(layout["opex_label_in_gap"])
        self.assertGreater(layout["opex_label_top"], 474.0)
        self.assertLess(layout["opex_label_top"] + 88.0, 590.0)

    def test_keeps_tax_label_below_short_net_profit_copy(self) -> None:
        layout = MODULE._right_profit_layout(
            net_height=80.0,
            tax_height=20.0,
            operating_bottom=440.0,
            opex_top=590.0,
            opex_bottom=650.0,
            other_height=12.0,
            other_bar_width=55.0,
            net_is_loss=False,
            other_inflow=True,
        )

        self.assertEqual(layout["net_top"], 310.0)
        self.assertGreaterEqual(layout["tax_top"], 480.0)

    def test_places_large_other_income_below_opex_with_external_label(self) -> None:
        layout = MODULE._right_profit_layout(
            net_height=299.0,
            tax_height=71.0,
            operating_bottom=474.0,
            opex_top=590.0,
            opex_bottom=678.0,
            other_height=261.0,
            other_bar_width=55.0,
            net_is_loss=False,
            other_inflow=True,
        )

        self.assertGreaterEqual(layout["other_source_top"], 706.0)
        self.assertLessEqual(layout["other_source_top"] + 261.0, 1005.0)
        self.assertFalse(layout["other_label_inside"])


if __name__ == "__main__":
    unittest.main()
