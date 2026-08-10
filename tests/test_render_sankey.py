from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image


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


class DestinationOrderedFlowSpansTests(unittest.TestCase):
    def test_assigns_source_spans_in_destination_order(self) -> None:
        spans = MODULE._destination_ordered_flow_spans(
            parent_top=100.0,
            parent_bottom=200.0,
            flows=[
                ("net", 50.0, 310.0),
                ("other", 10.0, 590.0),
                ("tax", 20.0, 520.0),
            ],
        )

        self.assertEqual(spans["net"], (100.0, 150.0))
        self.assertEqual(spans["tax"], (150.0, 170.0))
        self.assertEqual(spans["other"], (170.0, 180.0))


class NetLossFlowRegressionTests(unittest.TestCase):
    @staticmethod
    def _rendered_right_side_ribbons(data: dict) -> list[tuple]:
        ribbons: list[tuple] = []
        original_ribbon = MODULE._ribbon

        def capture_ribbon(*args, **kwargs):
            ribbons.append(args[1:8])
            return original_ribbon(*args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "net-loss.png"
            with mock.patch.object(MODULE, "_ribbon", side_effect=capture_ribbon):
                MODULE.render(data, output)

        return [ribbon for ribbon in ribbons if ribbon[0] >= 1400.0]

    def test_positive_operating_profit_can_offset_other_expense(self) -> None:
        sample_path = (
            ROOT
            / "income-statement-sankey/scripts/examples/intc_q2_2026_net_loss.json"
        )
        data = json.loads(sample_path.read_text())

        ribbons = self._rendered_right_side_ribbons(data)

        self.assertTrue(any(ribbon[6] == MODULE.GREEN_FLOW for ribbon in ribbons))

    def test_operating_loss_never_emits_green_profit_flow(self) -> None:
        sample_path = (
            ROOT
            / "income-statement-sankey/scripts/examples/intc_q2_2026_net_loss.json"
        )
        data = json.loads(sample_path.read_text())
        data["company"] = "Space Exploration Technologies Corp."
        data["ticker"] = "SPCX"
        data["period_label"] = "Q2 2026"
        data["period_end"] = "2026-06-30"
        data["operating_profit"] = {
            "amount": -0.143,
            "margin_pct": -1.83,
            "margin_yoy_pp": 21.997,
        }
        data["other_income"] = -0.375
        data["tax"] = 0.023
        data["net_profit"] = {
            "amount": -0.541,
            "margin_pct": -6.9235,
            "margin_yoy_pp": 17.837,
        }

        ribbons = self._rendered_right_side_ribbons(data)
        net_loss_ribbons = [
            ribbon
            for ribbon in ribbons
            if ribbon[3] == 1692.0 and 279.0 <= ribbon[4] < ribbon[5] <= 330.0
        ]

        self.assertEqual(len(net_loss_ribbons), 3)
        self.assertTrue(
            all(ribbon[6] == MODULE.RED_FLOW for ribbon in net_loss_ribbons)
        )
        self.assertEqual(
            sorted((ribbon[4], ribbon[5]) for ribbon in net_loss_ribbons),
            [(ribbon[4], ribbon[5]) for ribbon in net_loss_ribbons],
        )


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

    def test_moves_other_income_below_fallback_opex_label(self) -> None:
        layout = MODULE._right_profit_layout(
            net_height=80.0,
            tax_height=20.0,
            operating_bottom=570.0,
            opex_top=590.0,
            opex_bottom=630.0,
            other_height=120.0,
            other_bar_width=55.0,
            net_is_loss=False,
            other_inflow=True,
        )

        self.assertFalse(layout["opex_label_in_gap"])
        self.assertGreaterEqual(
            layout["other_source_top"],
            layout["opex_label_top"] + MODULE.EXPENSE_LABEL_HEIGHT + 20.0,
        )

    def test_moves_fallback_opex_and_short_other_labels_to_side_lane(self) -> None:
        layout = MODULE._right_profit_layout(
            net_height=245.9,
            tax_height=33.7,
            operating_bottom=615.7,
            opex_top=590.0,
            opex_bottom=609.4,
            other_height=28.9,
            other_bar_width=55.0,
            net_is_loss=False,
            other_inflow=True,
        )

        self.assertFalse(layout["opex_label_in_gap"])
        self.assertEqual(layout["opex_label_position"], "left")
        self.assertEqual(layout["other_label_position"], "left")
        self.assertGreaterEqual(
            layout["other_source_top"],
            layout["opex_label_top"] + MODULE.EXPENSE_LABEL_HEIGHT + 20.0,
        )

    def test_stacks_negative_other_below_tax_and_before_expense_details(self) -> None:
        layout = MODULE._right_profit_layout(
            net_height=217.6,
            tax_height=38.4,
            operating_bottom=621.7,
            opex_top=590.0,
            opex_bottom=603.4,
            other_height=0.0,
            other_bar_width=55.0,
            net_is_loss=False,
            other_inflow=False,
            other_outflow_height=10.0,
        )

        tax_bottom = layout["tax_top"] + 38.4
        self.assertGreaterEqual(layout["other_outflow_top"], tax_bottom + 20.0)
        self.assertGreaterEqual(
            layout["expense_start"],
            layout["other_outflow_top"] + MODULE.OTHER_LABEL_HEIGHT + 20.0,
        )

    def test_keeps_pre_opex_other_above_expense_detail_sources(self) -> None:
        pre_opex = MODULE._pre_opex_other_layout(
            operating_bottom=615.7,
            other_height=28.9,
            other_inflow=True,
        )
        opex_top = MODULE._expense_bar_top(
            baseline_top=590.0,
            upper_bottom=pre_opex["label_upper_bottom"],
        )
        opex_bottom = opex_top + 19.4
        layout = MODULE._right_profit_layout(
            net_height=245.9,
            tax_height=33.7,
            operating_bottom=pre_opex["label_upper_bottom"],
            opex_top=opex_top,
            opex_bottom=opex_bottom,
            other_height=28.9,
            other_bar_width=55.0,
            net_is_loss=False,
            other_inflow=True,
            other_source_top_override=pre_opex["other_source_top"],
        )

        self.assertTrue(pre_opex["other_above_opex"])
        self.assertLess(layout["other_source_top"] + 28.9, opex_top)
        self.assertGreaterEqual(layout["expense_start"], opex_bottom + 24.0)


class ExpenseLabelLayoutTests(unittest.TestCase):
    def test_moves_expense_bar_below_complete_label_gap(self) -> None:
        top = MODULE._expense_bar_top(
            baseline_top=590.0,
            upper_bottom=621.7,
        )

        self.assertGreaterEqual(
            top,
            621.7 + MODULE.EXPENSE_LABEL_HEIGHT + 2.0 * MODULE.LABEL_CLEARANCE,
        )

    def test_centers_label_inside_a_safe_gap(self) -> None:
        layout = MODULE._expense_label_layout(
            upper_bottom=474.0,
            expense_top=590.0,
            expense_bottom=678.0,
        )

        self.assertTrue(layout["in_gap"])
        self.assertGreaterEqual(layout["top"], 474.0 + MODULE.LABEL_CLEARANCE)
        self.assertLessEqual(
            layout["top"] + MODULE.EXPENSE_LABEL_HEIGHT,
            590.0 - MODULE.LABEL_CLEARANCE,
        )

    def test_places_label_below_expense_bar_when_gap_is_too_small(self) -> None:
        layout = MODULE._expense_label_layout(
            upper_bottom=700.0,
            expense_top=772.0,
            expense_bottom=820.0,
        )

        self.assertFalse(layout["in_gap"])
        self.assertGreaterEqual(layout["top"], 820.0 + MODULE.LABEL_CLEARANCE)


class ExpenseDetailDensityTests(unittest.TestCase):
    def test_keeps_full_metrics_with_generous_pitch(self) -> None:
        density = MODULE._expense_detail_density(125.0)

        self.assertTrue(density["show_pct"])
        self.assertTrue(density["show_pp"])
        self.assertFalse(density["combine_amount"])

    def test_hides_pp_before_percentage(self) -> None:
        density = MODULE._expense_detail_density(100.0)

        self.assertTrue(density["show_pct"])
        self.assertFalse(density["show_pp"])
        self.assertFalse(density["combine_amount"])

    def test_uses_compact_name_and_amount_for_sndk_pitch(self) -> None:
        density = MODULE._expense_detail_density(76.0)

        self.assertFalse(density["show_pct"])
        self.assertFalse(density["show_pp"])
        self.assertFalse(density["combine_amount"])
        self.assertLess(density["amount_base_offset"], 48.0)
        self.assertEqual(density["block_height"], 64.0)

    def test_combines_name_and_amount_for_dense_four_item_layout(self) -> None:
        density = MODULE._expense_detail_density(45.0)

        self.assertTrue(density["combine_amount"])
        self.assertFalse(density["show_pct"])
        self.assertFalse(density["show_pp"])

    def test_uses_remaining_space_to_separate_compact_details(self) -> None:
        tops = MODULE._expense_detail_tops(
            start=862.0,
            bottom=1025.0,
            count=2,
            block_height=64.0,
        )

        self.assertEqual(tops[0], 862.0)
        self.assertEqual(tops[1], 961.0)
        self.assertGreaterEqual(tops[1] - tops[0], 64.0)

    def test_dense_four_item_tops_leave_room_for_last_label(self) -> None:
        tops = MODULE._expense_detail_tops(
            start=820.0,
            bottom=1025.0,
            count=4,
            block_height=42.0,
        )

        self.assertEqual(tops[-1], 983.0)
        self.assertTrue(
            all(right - left >= 42.0 for left, right in zip(tops, tops[1:]))
        )


class SegmentLabelWidthTests(unittest.TestCase):
    def test_fits_long_segment_name_inside_left_column(self) -> None:
        MODULE._FONT_DPI = 160
        fig, ax = MODULE._figure(160)
        try:
            artist = ax.text(
                255.0,
                400.0,
                "High Performance\nComputing (HPC)",
                ha="right",
                va="center",
                linespacing=0.95,
                **MODULE._font(22, "bold"),
            )

            MODULE._fit_text_width(
                fig,
                artist,
                left=24.0,
                right=255.0,
            )
            extent = artist.get_window_extent(fig.canvas.get_renderer())

            self.assertGreaterEqual(extent.x0, 23.5)
            self.assertLessEqual(extent.x1, 255.5)
        finally:
            MODULE.plt.close(fig)


class SegmentMetricLayoutTests(unittest.TestCase):
    def test_keeps_top_segment_metrics_above_clear_label_block(self) -> None:
        layout = MODULE._segment_metric_layout(
            segment_top=235.0,
            segment_bottom=445.0,
            label_left=24.0,
            label_top=307.0,
            label_right=255.0,
            label_bottom=410.0,
            metric_left=276.0,
            metric_right=358.0,
        )

        self.assertEqual(layout["position"], "above")
        self.assertLessEqual(layout["bottom"], 307.0 - MODULE.LABEL_CLEARANCE)

    def test_keeps_bottom_metrics_above_when_columns_do_not_intersect(self) -> None:
        layout = MODULE._segment_metric_layout(
            segment_top=821.0,
            segment_bottom=859.0,
            label_left=24.0,
            label_top=810.0,
            label_right=255.0,
            label_bottom=910.0,
            metric_left=276.0,
            metric_right=358.0,
        )

        self.assertEqual(layout["position"], "above")
        self.assertLessEqual(layout["bottom"], 821.0)

    def test_moves_metrics_below_when_two_dimensional_bounds_overlap(self) -> None:
        layout = MODULE._segment_metric_layout(
            segment_top=821.0,
            segment_bottom=859.0,
            label_left=24.0,
            label_top=760.0,
            label_right=300.0,
            label_bottom=910.0,
            metric_left=276.0,
            metric_right=358.0,
        )

        self.assertEqual(layout["position"], "below")
        self.assertGreaterEqual(layout["top"], 910.0 + MODULE.LABEL_CLEARANCE)
        self.assertLessEqual(layout["bottom"], 1025.0)


class SegmentRenderRegressionTests(unittest.TestCase):
    def test_long_three_segment_labels_do_not_touch_canvas_edge(self) -> None:
        sample_path = (
            ROOT
            / "income-statement-sankey/scripts/examples/aapl_q3_fy26_full.json"
        )
        data = json.loads(sample_path.read_text())
        data["company"] = "TSMC"
        data["ticker"] = "TSM"
        data["segments"] = [
            {
                "name": "High Performance Computing (HPC)",
                "subtitle": "AI accelerators, GPUs, data center CPUs, networking",
                "revenue": 26.532,
                "yoy_pct": 36.0,
                "group": "hpc_smartphone",
            },
            {
                "name": "Smartphone",
                "subtitle": "Mobile SoCs, baseband, image processors",
                "revenue": 8.844,
                "yoy_pct": 36.0,
                "group": "hpc_smartphone",
            },
            {
                "name": "IoT / Automotive / DCE / Others",
                "subtitle": (
                    "Internet of Things, Automotive, Digital Consumer Electronics"
                ),
                "revenue": 4.824,
                "yoy_pct": 36.0,
                "group": "iot_etc",
            },
        ]
        data["revenue_groups"] = [
            {
                "id": "hpc_smartphone",
                "name": "HPC & Smartphone",
                "revenue": 35.376,
                "yoy_pct": 36.0,
            },
            {
                "id": "iot_etc",
                "name": "IoT, Auto, DCE, Others",
                "revenue": 4.824,
                "yoy_pct": 36.0,
            },
        ]
        data["total_revenue"] = {"revenue": 40.2, "yoy_pct": 36.0}

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "tsm.png"
            MODULE.render(data, output, dpi=160)
            image = Image.open(output).convert("RGB")

            for band_top, band_bottom in ((285, 430), (555, 665), (785, 1000)):
                dark_edge_pixels = 0
                for y in range(band_top, band_bottom):
                    for x in range(0, 8):
                        if max(image.getpixel((x, y))) < 125:
                            dark_edge_pixels += 1
                self.assertEqual(dark_edge_pixels, 0)

            for band_top, band_bottom in ((145, 220), (465, 540), (740, 805)):
                xs = []
                for y in range(band_top, band_bottom):
                    for x in range(265, 370):
                        if max(image.getpixel((x, y))) < 125:
                            xs.append(x)
                self.assertTrue(xs)
                self.assertAlmostEqual((min(xs) + max(xs)) / 2, 317.0, delta=8.0)


if __name__ == "__main__":
    unittest.main()
