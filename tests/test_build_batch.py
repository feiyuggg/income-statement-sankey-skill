from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BATCH_BUILDER = ROOT / "income-statement-sankey/scripts/build_batch.py"
SPEC = importlib.util.spec_from_file_location("build_batch", BATCH_BUILDER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BatchBuildTests(unittest.TestCase):
    def test_output_name_uses_source_stem(self) -> None:
        self.assertEqual(
            MODULE._output_path(Path("data/tsla-2026q2.json"), Path("out")),
            Path("out/tsla-2026q2.png"),
        )

    def test_cache_key_changes_with_source_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.json"
            source.write_text('{"value": 1}')
            first = MODULE._cache_key(source, 160)
            source.write_text('{"value": 2}')
            second = MODULE._cache_key(source, 160)
        self.assertNotEqual(first, second)

    def test_cache_requires_matching_key_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sample.png"
            output.write_bytes(b"png")
            MODULE._cache_path(output).write_text(json.dumps({"cache_key": "expected"}))
            self.assertTrue(MODULE._is_cached(output, "expected"))
            self.assertFalse(MODULE._is_cached(output, "different"))

    def test_same_stem_maps_to_same_output(self) -> None:
        out_dir = Path("out")
        self.assertEqual(
            MODULE._output_path(Path("first/q2.json"), out_dir),
            MODULE._output_path(Path("second/q2.json"), out_dir),
        )


if __name__ == "__main__":
    unittest.main()
