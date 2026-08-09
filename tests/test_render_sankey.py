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


if __name__ == "__main__":
    unittest.main()
