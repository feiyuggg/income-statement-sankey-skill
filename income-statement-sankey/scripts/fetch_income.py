#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "yfinance>=0.2.40",
#     "pandas>=2.0",
# ]
# ///
"""Fetch quarterly income-statement core lines from Yahoo Finance.

Segment (product-line) revenue is usually NOT on Yahoo. Pass --segments-json
or let the agent merge earnings-release segments into the output.

Usage:
  uv run fetch_income.py AAPL
  uv run fetch_income.py AAPL --quarter 0
  uv run fetch_income.py AAPL --out /tmp/aapl.json
  uv run fetch_income.py AAPL --segments-json segments.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yfinance as yf

# Row name candidates (yfinance labels vary slightly)
ROW_ALIASES: dict[str, list[str]] = {
    "revenue": ["Total Revenue", "Operating Revenue", "Revenue"],
    "cogs": ["Cost Of Revenue", "Reconciled Cost Of Revenue"],
    "gross_profit": ["Gross Profit"],
    "operating_income": ["Operating Income", "Total Operating Income As Reported"],
    "operating_expense": ["Operating Expense"],
    "rd": ["Research And Development", "Research & Development"],
    "sga": ["Selling General And Administration", "Selling General And Administrative"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
    "tax": ["Tax Provision"],
    "pretax": ["Pretax Income"],
    "other_income": ["Other Income Expense", "Other Non Operating Income Expenses"],
}


def _pick(series, keys: list[str]) -> float | None:
    for k in keys:
        if k in series.index:
            v = series[k]
            if v is not None and v == v:  # not NaN
                return float(v)
    return None


def _b(v: float | None) -> float | None:
    if v is None:
        return None
    return round(v / 1e9, 1)


def _pct(curr: float | None, prev: float | None) -> float | None:
    if curr is None or prev is None or prev == 0:
        return None
    return round((curr / prev - 1.0) * 100.0, 1)


def _pp(curr_ratio: float | None, prev_ratio: float | None) -> float | None:
    if curr_ratio is None or prev_ratio is None:
        return None
    return round((curr_ratio - prev_ratio) * 100.0, 1)  # ratios 0-1 → pp


def _fiscal_label(ticker: str, period_end: datetime, info: dict) -> tuple[str, str]:
    """Best-effort fiscal quarter label. Apple-like Sept year-end default when unknown."""
    month = period_end.month
    year = period_end.year
    # fiscalYearEnd e.g. "9-30"
    fye = (info or {}).get("fiscalYearEnd") or (info or {}).get("lastFiscalYearEnd")
    fy_end_month = 9
    if isinstance(fye, str) and "-" in fye:
        try:
            fy_end_month = int(fye.split("-")[0])
        except ValueError:
            pass
    elif isinstance(fye, (int, float)):
        # sometimes epoch — ignore
        pass

    # Map calendar month of quarter-end → fiscal quarter (for Sep FYE: Dec=Q1, Mar=Q2, Jun=Q3, Sep=Q4)
    # General: fiscal quarter ends months relative to FYE
    offset = (month - fy_end_month) % 12
    # quarter end offset 0 → Q4, 3 → Q1, 6 → Q2, 9 → Q3 for standard
    q_map = {0: 4, 3: 1, 6: 2, 9: 3}
    fq = q_map.get(offset)
    if fq is None:
        # fallback calendar quarter
        fq = (month - 1) // 3 + 1
        fy = year
    else:
        # fiscal year is calendar year of FYE month
        if month > fy_end_month:
            fy = year + 1
        else:
            fy = year
        # For Sep FYE: Jun 2026 → month 6 < 9 → FY26, Q3 ✓
        if month <= fy_end_month:
            fy = year if fy_end_month == 12 else (
                year if month <= fy_end_month else year + 1
            )
        # cleaner: FY label year = year of next (or current) FYE
        if month > fy_end_month:
            fy = year + 1
        else:
            fy = year

    # Apple convention: period ending June 2026 = Q3 FY26
    if fy_end_month == 9:
        if month == 12:
            fq, fy = 1, year + 1
        elif month == 3:
            fq, fy = 2, year
        elif month == 6:
            fq, fy = 3, year
        elif month == 9:
            fq, fy = 4, year

    period_label = f"Q{fq} FY{str(fy)[2:]}"
    period_end_label = f"Ending {period_end.strftime('%B %Y')}"
    return period_label, period_end_label


def fetch(ticker: str, quarter_index: int = 0, segments: list[dict] | None = None) -> dict[str, Any]:
    t = yf.Ticker(ticker)
    info = t.info or {}
    q = t.quarterly_income_stmt
    if q is None or q.empty:
        raise SystemExit(f"No quarterly income statement for {ticker}")

    cols = list(q.columns)
    if quarter_index < 0 or quarter_index >= len(cols):
        raise SystemExit(f"quarter index {quarter_index} out of range (0..{len(cols)-1})")

    col = cols[quarter_index]
    # YoY: same calendar quarter prior year
    yoy_col = None
    target = col
    if hasattr(col, "year"):
        for c in cols:
            if hasattr(c, "year") and c.year == col.year - 1 and c.month == col.month and c.day == col.day:
                yoy_col = c
                break
        if yoy_col is None:
            # nearest same month prior year
            for c in cols:
                if hasattr(c, "year") and c.year == col.year - 1 and c.month == col.month:
                    yoy_col = c
                    break

    cur = q[col]
    prev = q[yoy_col] if yoy_col is not None else None

    def line(key: str) -> tuple[float | None, float | None, float | None]:
        c = _pick(cur, ROW_ALIASES[key])
        p = _pick(prev, ROW_ALIASES[key]) if prev is not None else None
        return c, p, _pct(c, p)

    rev, rev_p, rev_yoy = line("revenue")
    cogs, cogs_p, _ = line("cogs")
    gp, gp_p, _ = line("gross_profit")
    oi, oi_p, _ = line("operating_income")
    opex, opex_p, _ = line("operating_expense")
    rd, rd_p, _ = line("rd")
    sga, sga_p, _ = line("sga")
    ni, ni_p, _ = line("net_income")
    tax, tax_p, _ = line("tax")
    other, other_p, _ = line("other_income")

    # derive missing
    if gp is None and rev is not None and cogs is not None:
        gp = rev - cogs
    if cogs is None and rev is not None and gp is not None:
        cogs = rev - gp
    if opex is None and gp is not None and oi is not None:
        opex = gp - oi
    if rd is None and sga is not None and opex is not None:
        rd = opex - sga
    if sga is None and rd is not None and opex is not None:
        sga = opex - rd

    def margin(num, den):
        if num is None or den is None or den == 0:
            return None
        return num / den

    gp_m = margin(gp, rev)
    gp_m_p = margin(gp_p, rev_p) if prev is not None else None
    oi_m = margin(oi, rev)
    oi_m_p = margin(oi_p, rev_p) if prev is not None else None
    ni_m = margin(ni, rev)
    ni_m_p = margin(ni_p, rev_p) if prev is not None else None
    rd_r = margin(rd, rev)
    rd_r_p = margin(rd_p, rev_p) if prev is not None else None
    sga_r = margin(sga, rev)
    sga_r_p = margin(sga_p, rev_p) if prev is not None else None

    period_end = col.to_pydatetime() if hasattr(col, "to_pydatetime") else datetime.fromisoformat(str(col)[:10])
    period_label, period_end_label = _fiscal_label(ticker, period_end, info)
    company = info.get("shortName") or info.get("longName") or ticker
    # clean "Apple Inc." → "Apple"
    for suffix in (" Inc.", " Inc", " Corporation", " Corp.", " Corp", " plc", " Ltd.", " Limited"):
        if company.endswith(suffix):
            company = company[: -len(suffix)].strip()

    products = None
    services = None
    seg_out: list[dict] = []
    if segments:
        prod_sum = 0.0
        svc_sum = 0.0
        for s in segments:
            g = (s.get("group") or "products").lower()
            r = float(s["revenue"])
            item = {
                "name": s["name"],
                "revenue": round(r, 1),
                "yoy_pct": s.get("yoy_pct"),
                "group": g,
                "subtitle": s.get("subtitle"),
            }
            seg_out.append(item)
            if g == "services":
                svc_sum += r
            else:
                prod_sum += r
        products = {
            "revenue": round(prod_sum, 1),
            "yoy_pct": next((s.get("yoy_pct") for s in segments if s.get("is_products_total")), None),
        }
        # allow explicit products/services totals override
        for s in segments:
            if s.get("is_products_total"):
                products = {"revenue": float(s["revenue"]), "yoy_pct": s.get("yoy_pct")}
            if s.get("is_services_total"):
                services = {"revenue": float(s["revenue"]), "yoy_pct": s.get("yoy_pct")}
        if services is None and svc_sum > 0:
            services = {"revenue": round(svc_sum, 1), "yoy_pct": None}
        if products is not None and products.get("yoy_pct") is None:
            products["yoy_pct"] = None

    # Optional product/services COGS from segments file extras
    cogs_products = None
    cogs_services = None
    products_gm = None
    services_gm = None
    if segments:
        meta = next((s for s in segments if s.get("_meta")), None)

    data: dict[str, Any] = {
        "company": company,
        "ticker": ticker.upper(),
        "period_label": period_label,
        "period_end_label": period_end_label,
        "period_end": period_end.strftime("%Y-%m-%d"),
        "currency": info.get("currency") or "USD",
        "unit": "B",
        "source_notes": [
            "yfinance quarterly_income_stmt",
            f"column={col}",
            f"yoy_column={yoy_col}",
        ],
        "source_records": [
            {
                "label": "Yahoo Finance quarterly income statement",
                "type": "aggregator",
                "url": f"https://finance.yahoo.com/quote/{ticker.upper()}/financials/",
            }
        ],
        "segments": seg_out,
        "products": products,
        "services": services,
        "total_revenue": {"revenue": _b(rev), "yoy_pct": rev_yoy},
        "gross_profit": {
            "amount": _b(gp),
            "margin_pct": round(gp_m * 100, 0) if gp_m is not None else None,
            "margin_yoy_pp": round(_pp(gp_m, gp_m_p), 0) if _pp(gp_m, gp_m_p) is not None else None,
        },
        "cogs": {
            "amount": _b(cogs),
            "products": cogs_products,
            "products_gm_pct": products_gm,
            "services": cogs_services,
            "services_gm_pct": services_gm,
        },
        "operating_profit": {
            "amount": _b(oi),
            "margin_pct": round(oi_m * 100, 0) if oi_m is not None else None,
            "margin_yoy_pp": round(_pp(oi_m, oi_m_p), 0) if _pp(oi_m, oi_m_p) is not None else None,
        },
        "opex": {
            "amount": _b(opex),
            "rd": _b(rd),
            "rd_pct_rev": round(rd_r * 100, 0) if rd_r is not None else None,
            "rd_yoy_pp": round(_pp(rd_r, rd_r_p), 0) if _pp(rd_r, rd_r_p) is not None else None,
            "sga": _b(sga),
            "sga_pct_rev": round(sga_r * 100, 0) if sga_r is not None else None,
            "sga_yoy_pp": round(_pp(sga_r, sga_r_p), 0) if _pp(sga_r, sga_r_p) is not None else None,
        },
        "net_profit": {
            "amount": _b(ni),
            "margin_pct": round(ni_m * 100, 0) if ni_m is not None else None,
            "margin_yoy_pp": round(_pp(ni_m, ni_m_p), 0) if _pp(ni_m, ni_m_p) is not None else None,
        },
        "tax": _b(tax),
        "other_income": _b(other),
        "raw_usd": {
            "revenue": rev,
            "cogs": cogs,
            "gross_profit": gp,
            "operating_income": oi,
            "operating_expense": opex,
            "rd": rd,
            "sga": sga,
            "net_income": ni,
            "tax": tax,
            "other_income": other,
        },
    }
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch income statement for sankey chart")
    ap.add_argument("ticker", help="Stock ticker, e.g. AAPL")
    ap.add_argument("--quarter", type=int, default=0, help="0=latest quarter, 1=prior, ...")
    ap.add_argument("--segments-json", type=Path, help="Optional segment breakdown JSON array")
    ap.add_argument("--out", type=Path, help="Write JSON to this path (default stdout)")
    args = ap.parse_args()

    segments = None
    if args.segments_json:
        segments = json.loads(args.segments_json.read_text())
        if isinstance(segments, dict) and "segments" in segments:
            # allow full data file merge later
            segments = segments["segments"]

    data = fetch(args.ticker, args.quarter, segments)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
