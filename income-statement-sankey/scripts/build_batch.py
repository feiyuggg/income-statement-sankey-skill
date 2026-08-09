#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "matplotlib>=3.8",
#     "pillow>=10",
# ]
# ///
"""Validate and render one or more verified Sankey JSON files in parallel."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from validate_data import validate  # type: ignore


def _output_path(source: Path, out_dir: Path) -> Path:
    return out_dir / f"{source.stem}.png"


def _cache_path(output: Path) -> Path:
    return output.with_suffix(".sankey-cache.json")


def _cache_key(source: Path, dpi: int) -> str:
    digest = hashlib.sha256()
    digest.update(source.read_bytes())
    for dependency in (SCRIPT_DIR / "render_sankey.py", SCRIPT_DIR / "validate_data.py"):
        digest.update(dependency.read_bytes())
    digest.update(f"dpi={dpi}".encode())
    return digest.hexdigest()


def _is_cached(output: Path, cache_key: str) -> bool:
    cache = _cache_path(output)
    if not output.is_file() or not cache.is_file():
        return False
    try:
        payload = json.loads(cache.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return payload.get("cache_key") == cache_key


def _render_one(source_text: str, output_text: str, dpi: int, cache_key: str) -> str:
    from render_sankey import render  # type: ignore

    source = Path(source_text)
    output = Path(output_text)
    data = json.loads(source.read_text())
    render(data, output, dpi=dpi)
    _cache_path(output).write_text(
        json.dumps(
            {"cache_key": cache_key, "source": str(source), "dpi": dpi},
            indent=2,
        )
        + "\n"
    )
    return str(output)


def _load_and_validate(source: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        data = json.loads(source.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return None, [str(exc)]
    return data, validate(data)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and render verified Sankey JSON files in parallel"
    )
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=0, help="0 selects an automatic value")
    parser.add_argument("--dpi", type=int, default=160)
    parser.add_argument("--force", action="store_true", help="ignore render cache")
    args = parser.parse_args()

    sources = [path.resolve() for path in args.inputs]
    missing = [str(path) for path in sources if not path.is_file()]
    if missing:
        parser.error(f"input files not found: {', '.join(missing)}")

    validation_failed = False
    for source in sources:
        _, errors = _load_and_validate(source)
        if errors:
            validation_failed = True
            for error in errors:
                print(f"validation error [{source.name}]: {error}", file=sys.stderr)
    if validation_failed:
        raise SystemExit(1)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    outputs = [_output_path(source, args.out_dir) for source in sources]
    duplicate_outputs = sorted(
        {str(output) for output in outputs if outputs.count(output) > 1}
    )
    if duplicate_outputs:
        parser.error(
            "input filenames must have unique stems; output collisions: "
            + ", ".join(duplicate_outputs)
        )

    pending: list[tuple[Path, Path, str]] = []
    for source, output in zip(sources, outputs):
        cache_key = _cache_key(source, args.dpi)
        if not args.force and _is_cached(output, cache_key):
            print(f"CACHED {output}")
        else:
            pending.append((source, output, cache_key))

    if not pending:
        return

    jobs = args.jobs or min(len(pending), os.cpu_count() or 1, 6)
    jobs = max(1, min(jobs, len(pending)))
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        futures = {
            executor.submit(_render_one, str(source), str(output), args.dpi, cache_key): source
            for source, output, cache_key in pending
        }
        for future in as_completed(futures):
            source = futures[future]
            try:
                print(f"RENDERED {future.result()}")
            except Exception as exc:
                print(f"render error [{source.name}]: {exc}", file=sys.stderr)
                for other in futures:
                    other.cancel()
                raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
