#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "yfinance>=0.2.40",
#     "pandas>=2.0",
#     "matplotlib>=3.8",
#     "numpy>=1.26",
# ]
# ///
"""One-shot: fetch income data (+ optional segments) and render sankey PNG.

Usage:
  uv run build_chart.py AAPL -o aapl.png
  uv run build_chart.py AAPL --quarter 0 --segments segments.json -o aapl.png
  uv run build_chart.py --from-json full_data.json -o out.png
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow sibling imports when run as script path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_income import fetch  # type: ignore
from render_sankey import render  # type: ignore
from validate_data import validate  # type: ignore


def merge_segments(data: dict, segments_payload) -> dict:
    """Merge segment list or partial overlay into fetched data."""
    if segments_payload is None:
        return data
    if isinstance(segments_payload, dict) and "segments" in segments_payload:
        # full or partial data overlay
        overlay = segments_payload
        for k, v in overlay.items():
            if k == "segments":
                continue
            if v is not None:
                data[k] = v
        segments_payload = overlay.get("segments")

    if not segments_payload:
        return data

    segs = []
    prod_sum = 0.0
    svc_sum = 0.0
    products_total = None
    services_total = None
    for s in segments_payload:
        if s.get("is_products_total"):
            products_total = {"revenue": float(s["revenue"]), "yoy_pct": s.get("yoy_pct")}
            continue
        if s.get("is_services_total"):
            services_total = {"revenue": float(s["revenue"]), "yoy_pct": s.get("yoy_pct")}
            continue
        if s.get("_meta"):
            meta = s
            if "cogs_products" in meta:
                data.setdefault("cogs", {})["products"] = meta["cogs_products"]
            if "cogs_services" in meta:
                data.setdefault("cogs", {})["services"] = meta["cogs_services"]
            if "products_gm_pct" in meta:
                data.setdefault("cogs", {})["products_gm_pct"] = meta["products_gm_pct"]
            if "services_gm_pct" in meta:
                data.setdefault("cogs", {})["services_gm_pct"] = meta["services_gm_pct"]
            continue
        g = (s.get("group") or "products").lower()
        r = float(s["revenue"])
        segs.append({
            "name": s["name"],
            "revenue": round(r, 1),
            "yoy_pct": s.get("yoy_pct"),
            "group": g,
            "subtitle": s.get("subtitle"),
        })
        if g == "services":
            svc_sum += r
        else:
            prod_sum += r

    data["segments"] = segs
    if products_total:
        data["products"] = products_total
    elif prod_sum > 0:
        data["products"] = {"revenue": round(prod_sum, 1), "yoy_pct": data.get("products", {}) and data["products"].get("yoy_pct")}
    if services_total:
        data["services"] = services_total
    elif svc_sum > 0:
        data["services"] = {"revenue": round(svc_sum, 1), "yoy_pct": None}

    # COGS GM if products/services COGS present
    cogs = data.get("cogs") or {}
    prod = data.get("products") or {}
    svc = data.get("services") or {}
    if cogs.get("products") is not None and prod.get("revenue"):
        cogs["products_gm_pct"] = cogs.get("products_gm_pct") or round(
            (1 - float(cogs["products"]) / float(prod["revenue"])) * 100, 0
        )
    if cogs.get("services") is not None and svc.get("revenue"):
        cogs["services_gm_pct"] = cogs.get("services_gm_pct") or round(
            (1 - float(cogs["services"]) / float(svc["revenue"])) * 100, 0
        )
    data["cogs"] = cogs

    if data.get("products") or data.get("services"):
        groups = []
        if data.get("products") and data["products"].get("revenue") is not None:
            groups.append({
                "id": "products",
                "name": "Products",
                "revenue": data["products"]["revenue"],
                "yoy_pct": data["products"].get("yoy_pct"),
            })
        if data.get("services") and data["services"].get("revenue") is not None:
            groups.append({
                "id": "services",
                "name": "Services",
                "revenue": data["services"]["revenue"],
                "yoy_pct": data["services"].get("yoy_pct"),
            })
        data["revenue_groups"] = groups

    notes = data.setdefault("source_notes", [])
    notes.append("segments: user/agent-supplied")
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description="Build income-statement sankey chart")
    ap.add_argument("ticker", nargs="?", help="Ticker symbol (omit with --from-json)")
    ap.add_argument("--quarter", type=int, default=0)
    ap.add_argument("--segments", type=Path, help="Segments JSON array or overlay object")
    ap.add_argument("--from-json", type=Path, help="Skip fetch; render this complete JSON")
    ap.add_argument("--save-json", type=Path, help="Also write merged JSON")
    ap.add_argument(
        "--validate",
        action="store_true",
        help="Fail unless identities and official-source metadata validate",
    )
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--dpi", type=int, default=160)
    args = ap.parse_args()

    if args.from_json:
        data = json.loads(args.from_json.read_text())
    else:
        if not args.ticker:
            ap.error("ticker required unless --from-json")
        segs = None
        if args.segments:
            segs = json.loads(args.segments.read_text())
        data = fetch(args.ticker, args.quarter, None)
        if segs is not None:
            data = merge_segments(data, segs)

    if args.validate:
        errors = validate(data)
        if errors:
            for error in errors:
                print(f"validation error: {error}", file=sys.stderr)
            raise SystemExit(1)

    if args.save_json:
        args.save_json.parent.mkdir(parents=True, exist_ok=True)
        args.save_json.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    path = render(data, args.out, dpi=args.dpi)
    print(path)


if __name__ == "__main__":
    main()
