#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# ///
"""Validate income-statement Sankey JSON before rendering."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


OFFICIAL_SOURCE_TYPES = {
    "official_ir",
    "regulatory_filing",
    "annual_report",
    "quarterly_report",
}
AGGREGATOR_HOSTS = {
    "finance.yahoo.com",
    "companiesmarketcap.com",
    "macrotrends.net",
    "marketscreener.com",
    "stockanalysis.com",
}
INVALID_HOST_SUFFIXES = (".example", ".invalid", ".localhost", ".test")


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _nested(data: dict[str, Any], *keys: str) -> float | None:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return _num(value)


def _require_number(
    errors: list[str],
    data: dict[str, Any],
    *keys: str,
    positive: bool = False,
) -> float | None:
    value = _nested(data, *keys)
    path = ".".join(keys)
    if value is None:
        errors.append(f"missing required number: {path}")
    elif positive and value <= 0:
        errors.append(f"{path} must be positive")
    return value


def _valid_date(value: Any) -> bool:
    try:
        dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return False
    return True


def _validate_source_record(record: dict[str, Any], index: int) -> list[str]:
    errors: list[str] = []
    prefix = f"source_records[{index}]"
    source_type = str(record.get("type") or "").strip().lower()
    if source_type not in OFFICIAL_SOURCE_TYPES | {"aggregator"}:
        errors.append(f"{prefix}.type is unsupported: {source_type or '<missing>'}")

    for field in ("label", "publisher", "url", "retrieved_on"):
        if not str(record.get(field) or "").strip():
            errors.append(f"missing required text field: {prefix}.{field}")

    if record.get("retrieved_on") and not _valid_date(record["retrieved_on"]):
        errors.append(f"{prefix}.retrieved_on must use YYYY-MM-DD")

    parsed = urlparse(str(record.get("url") or ""))
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        errors.append(f"{prefix}.url must be an absolute HTTPS URL")
    elif (
        host.endswith(INVALID_HOST_SUFFIXES) or host in AGGREGATOR_HOSTS
    ) and source_type in OFFICIAL_SOURCE_TYPES:
        errors.append(
            f"{prefix}.url host is not acceptable for an official source: {host}"
        )

    return errors


def _validate_conglomerate(
    data: dict[str, Any],
    revenue: float,
    tol: float,
    yoy_tol: float,
    ratio_tol: float,
    identity: Any,
) -> list[str]:
    """Checks for `layout.style == "conglomerate"`.

    Insurers, banks, and holding companies report business segments rather than
    a product/service split, and have no meaningful gross profit or R&D line.
    This branch drops those requirements and instead ties the segment footnote
    to the consolidated totals, so the numbers still cannot be fabricated:
    segment profits must sum to operating profit, and every Y/Y and margin
    change is recomputed from `prior_period`.
    """
    errors: list[str] = []

    segments = data.get("segments")
    if not isinstance(segments, list) or len(segments) < 2:
        errors.append("segments must contain at least two reported business segments")
        segments = []

    names: set[str] = set()
    revenue_sum = 0.0
    profit_sum = 0.0
    profits_complete = bool(segments)
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            errors.append(f"segments[{index}] must be an object")
            profits_complete = False
            continue
        name = str(segment.get("name") or "").strip()
        value = _num(segment.get("revenue"))
        profit = _num(segment.get("profit"))
        yoy = _num(segment.get("yoy_pct"))
        margin = _num(segment.get("margin_pct"))
        if not name:
            errors.append(f"segments[{index}].name is required")
        elif name in names:
            errors.append(f"duplicate segment name: {name}")
        else:
            names.add(name)
        if value is None or value <= 0:
            errors.append(f"segments[{index}].revenue must be positive")
        else:
            revenue_sum += value
        if yoy is None:
            errors.append(f"missing required number: segments[{index}].yoy_pct")
        if margin is None:
            errors.append(f"missing required number: segments[{index}].margin_pct")
        if profit is None:
            profits_complete = False
        else:
            profit_sum += profit
            if margin is not None and value:
                expected = profit / value * 100
                if abs(expected - margin) > ratio_tol:
                    errors.append(
                        f"segments[{index}].margin_pct is {margin:.2f}, "
                        f"expected {expected:.2f}"
                    )

    other_revenue = _nested(data, "revenue_other", "amount")
    if data.get("revenue_other") is not None and (
        other_revenue is None or other_revenue <= 0
    ):
        errors.append("revenue_other.amount must be positive when present")
    identity(
        "segments + revenue_other -> total revenue",
        revenue_sum + (other_revenue or 0.0),
        revenue,
    )

    operating_profit = _require_number(
        errors, data, "operating_profit", "amount", positive=True
    )
    operating_costs = _require_number(
        errors, data, "operating_costs", "amount", positive=True
    )
    identity(
        "operating profit + operating costs -> total revenue",
        None
        if operating_profit is None or operating_costs is None
        else operating_profit + operating_costs,
        revenue,
    )
    if profits_complete:
        identity("segment profits -> operating profit", profit_sum, operating_profit)
    else:
        errors.append(
            "every segment requires a profit figure so operating profit can be verified"
        )

    invest = _nested(data, "investment_gains", "amount")
    if invest is None:
        errors.append("missing required number: investment_gains.amount")
    other_income = _num(data.get("other_income"))
    if other_income is None:
        errors.append("missing required number: other_income")
    pretax = _require_number(errors, data, "pretax_profit", "amount", positive=True)
    identity(
        "operating profit + investment gains + other -> pre-tax profit",
        None
        if operating_profit is None or invest is None or other_income is None
        else operating_profit + invest + other_income,
        pretax,
    )

    net_profit = _require_number(errors, data, "net_profit", "amount", positive=True)
    tax = _num(data.get("tax"))
    if tax is None:
        errors.append("missing required number: tax")
    identity(
        "net profit + tax -> pre-tax profit",
        None if net_profit is None or tax is None else net_profit + tax,
        pretax,
    )

    for path, amount in (
        ("operating_profit", operating_profit),
        ("net_profit", net_profit),
    ):
        margin = _nested(data, path, "margin_pct")
        if margin is None:
            errors.append(f"missing required number: {path}.margin_pct")
        elif amount is not None:
            expected = amount / revenue * 100
            if abs(expected - margin) > ratio_tol:
                errors.append(
                    f"{path}.margin_pct is {margin:.2f}, expected {expected:.2f}"
                )

    prior = data.get("prior_period")
    if not isinstance(prior, dict):
        errors.append("prior_period is required to verify YoY and margin changes")
        prior = {}
    prior_revenue = _num(prior.get("total_revenue"))
    if prior_revenue is None or prior_revenue <= 0:
        errors.append("prior_period.total_revenue must be positive")

    def check_yoy(label: str, current: float | None, previous: float | None,
                  reported: float | None) -> None:
        if previous is None or previous <= 0:
            errors.append(f"missing or invalid prior value for {label}")
            return
        if current is None or reported is None:
            errors.append(f"missing current value or YoY metric for {label}")
            return
        expected = (current / previous - 1.0) * 100
        if abs(expected - reported) > yoy_tol:
            errors.append(f"{label} YoY is {reported:.2f}, expected {expected:.2f}")

    check_yoy(
        "total_revenue", revenue, prior_revenue, _nested(data, "total_revenue", "yoy_pct")
    )

    prior_segments = {
        str(item.get("name") or ""): _num(item.get("revenue"))
        for item in prior.get("segments") or []
        if isinstance(item, dict)
    }
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        name = str(segment.get("name") or "")
        check_yoy(
            f"segments[{name}]",
            _num(segment.get("revenue")),
            prior_segments.get(name),
            _num(segment.get("yoy_pct")),
        )

    for path, amount in (
        ("operating_profit", operating_profit),
        ("net_profit", net_profit),
    ):
        reported = _nested(data, path, "margin_yoy_pp")
        prior_amount = _num(prior.get(path))
        if reported is None:
            errors.append(f"missing required number: {path}.margin_yoy_pp")
        elif prior_amount is None or prior_revenue is None or prior_revenue <= 0:
            errors.append(f"missing prior value required to verify {path}.margin_yoy_pp")
        elif amount is not None:
            expected = amount / revenue * 100 - prior_amount / prior_revenue * 100
            if abs(expected - reported) > yoy_tol:
                errors.append(
                    f"{path}.margin_yoy_pp is {reported:.2f}, expected {expected:.2f}"
                )

    source_records = data.get("source_records")
    if not isinstance(source_records, list) or not source_records:
        errors.append("source_records must include at least one source")
    else:
        for index, record in enumerate(source_records):
            if not isinstance(record, dict):
                errors.append(f"source_records[{index}] must be an object")
                continue
            errors.extend(_validate_source_record(record, index))
        if not any(
            str(record.get("type") or "").lower() in OFFICIAL_SOURCE_TYPES
            for record in source_records
            if isinstance(record, dict)
        ):
            errors.append("source_records must include an official or regulatory source")

    return errors


def validate(data: dict[str, Any], tolerance: float | None = None) -> list[str]:
    errors: list[str] = []
    required_text = ("company", "period_label", "period_end_label", "currency", "unit")
    for field in required_text:
        if not str(data.get(field) or "").strip():
            errors.append(f"missing required text field: {field}")

    revenue = _nested(data, "total_revenue", "revenue")
    if revenue is None or revenue <= 0:
        errors.append("total_revenue.revenue must be a positive number")
        return errors

    tol = tolerance if tolerance is not None else max(0.01, revenue * 0.0001)
    yoy_tol = 0.2
    ratio_tol = 0.15

    def identity(label: str, left: float | None, right: float | None) -> None:
        if left is None or right is None:
            errors.append(f"{label} cannot be checked because a required value is missing")
            return
        if abs(left - right) > tol:
            errors.append(
                f"{label} does not reconcile: {left:.3f} vs {right:.3f} "
                f"(difference {abs(left - right):.3f}, tolerance {tol:.3f})"
            )

    if str((data.get("layout") or {}).get("style") or "").lower() == "conglomerate":
        errors.extend(
            _validate_conglomerate(data, revenue, tol, yoy_tol, ratio_tol, identity)
        )
        return errors

    groups = data.get("revenue_groups")
    if not isinstance(groups, list) or len(groups) < 2:
        errors.append("revenue_groups must contain at least two reported revenue components")
        groups = []

    group_ids: set[str] = set()
    group_values: dict[str, float] = {}
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            errors.append(f"revenue_groups[{index}] must be an object")
            continue
        group_id = str(group.get("id") or "").strip()
        name = str(group.get("name") or "").strip()
        value = _num(group.get("revenue"))
        yoy = _num(group.get("yoy_pct"))
        if not group_id or not name:
            errors.append(f"revenue_groups[{index}] requires id and name")
        elif group_id in group_ids:
            errors.append(f"duplicate revenue group id: {group_id}")
        else:
            group_ids.add(group_id)
        if value is None or value <= 0:
            errors.append(f"revenue_groups[{index}].revenue must be positive")
        elif group_id:
            group_values[group_id] = value
        if yoy is None:
            errors.append(f"missing required number: revenue_groups[{index}].yoy_pct")

    if groups:
        identity("revenue_groups -> total revenue", sum(group_values.values()), revenue)

    segments = data.get("segments") or []
    segment_names: set[str] = set()
    segment_group_sums: dict[str, float] = {}
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            errors.append(f"segments[{index}] must be an object")
            continue
        name = str(segment.get("name") or "").strip()
        group_id = str(segment.get("group") or "").strip()
        value = _num(segment.get("revenue"))
        yoy = _num(segment.get("yoy_pct"))
        if not name:
            errors.append(f"segments[{index}].name is required")
        elif name in segment_names:
            errors.append(f"duplicate segment name: {name}")
        else:
            segment_names.add(name)
        if group_id not in group_ids:
            errors.append(
                f"segments[{index}].group does not match a revenue group: {group_id}"
            )
        if value is None or value <= 0:
            errors.append(f"segments[{index}].revenue must be positive")
        else:
            segment_group_sums[group_id] = (
                segment_group_sums.get(group_id, 0.0) + value
            )
        if yoy is None:
            errors.append(f"missing required number: segments[{index}].yoy_pct")

    for group_id, segment_sum in segment_group_sums.items():
        identity(
            f"segments[{group_id}] -> revenue group",
            segment_sum,
            group_values.get(group_id),
        )

    gross_profit = _require_number(errors, data, "gross_profit", "amount", positive=True)
    cogs = _require_number(errors, data, "cogs", "amount", positive=True)
    identity(
        "gross profit + COGS -> total revenue",
        None if gross_profit is None or cogs is None else gross_profit + cogs,
        revenue,
    )

    operating_profit = _require_number(
        errors, data, "operating_profit", "amount", positive=True
    )
    opex = _require_number(errors, data, "opex", "amount", positive=True)
    identity(
        "operating profit + operating expenses -> gross profit",
        None if operating_profit is None or opex is None else operating_profit + opex,
        gross_profit,
    )

    rd = _require_number(errors, data, "opex", "rd", positive=True)
    sga = _require_number(errors, data, "opex", "sga", positive=True)
    identity(
        "R&D + SG&A -> operating expenses",
        None if rd is None or sga is None else rd + sga,
        opex,
    )

    net_profit = _require_number(errors, data, "net_profit", "amount")
    tax = _num(data.get("tax"))
    other = _num(data.get("other_income"))
    if tax is None:
        errors.append("missing required number: tax")
    if other is None:
        errors.append("missing required number: other_income")
    identity(
        "operating profit + other income -> net profit + tax",
        None if operating_profit is None or other is None else operating_profit + other,
        None if net_profit is None or tax is None else net_profit + tax,
    )

    for path, amount, margin in (
        ("gross_profit", gross_profit, _nested(data, "gross_profit", "margin_pct")),
        (
            "operating_profit",
            operating_profit,
            _nested(data, "operating_profit", "margin_pct"),
        ),
        ("net_profit", net_profit, _nested(data, "net_profit", "margin_pct")),
    ):
        if margin is None:
            errors.append(f"missing required number: {path}.margin_pct")
        elif amount is not None:
            expected = amount / revenue * 100
            if abs(expected - margin) > ratio_tol:
                errors.append(f"{path}.margin_pct is {margin:.2f}, expected {expected:.2f}")

    for field, amount in (("rd_pct_rev", rd), ("sga_pct_rev", sga)):
        ratio = _nested(data, "opex", field)
        if ratio is None:
            errors.append(f"missing required number: opex.{field}")
        elif amount is not None:
            expected = amount / revenue * 100
            if abs(expected - ratio) > ratio_tol:
                errors.append(f"opex.{field} is {ratio:.2f}, expected {expected:.2f}")

    prior = data.get("prior_period")
    if not isinstance(prior, dict):
        errors.append("prior_period is required to verify YoY and margin changes")
        prior = {}
    prior_revenue = _num(prior.get("total_revenue"))
    if prior_revenue is None or prior_revenue <= 0:
        errors.append("prior_period.total_revenue must be positive")

    def check_yoy(
        label: str,
        current: float | None,
        previous: float | None,
        reported: float | None,
    ) -> None:
        if previous is None or previous <= 0:
            errors.append(f"missing or invalid prior value for {label}")
            return
        if current is None or reported is None:
            errors.append(f"missing current value or YoY metric for {label}")
            return
        expected = (current / previous - 1.0) * 100
        if abs(expected - reported) > yoy_tol:
            errors.append(f"{label} YoY is {reported:.2f}, expected {expected:.2f}")

    check_yoy(
        "total_revenue",
        revenue,
        prior_revenue,
        _nested(data, "total_revenue", "yoy_pct"),
    )

    prior_groups = {
        str(item.get("id") or ""): _num(item.get("revenue"))
        for item in prior.get("revenue_groups") or []
        if isinstance(item, dict)
    }
    for group in groups:
        group_id = str(group.get("id") or "")
        check_yoy(
            f"revenue_groups[{group_id}]",
            _num(group.get("revenue")),
            prior_groups.get(group_id),
            _num(group.get("yoy_pct")),
        )

    prior_segments = {
        str(item.get("name") or ""): _num(item.get("revenue"))
        for item in prior.get("segments") or []
        if isinstance(item, dict)
    }
    for segment in segments:
        name = str(segment.get("name") or "")
        check_yoy(
            f"segments[{name}]",
            _num(segment.get("revenue")),
            prior_segments.get(name),
            _num(segment.get("yoy_pct")),
        )

    margin_checks = (
        (
            "gross_profit.margin_yoy_pp",
            gross_profit,
            _num(prior.get("gross_profit")),
            _nested(data, "gross_profit", "margin_yoy_pp"),
        ),
        (
            "operating_profit.margin_yoy_pp",
            operating_profit,
            _num(prior.get("operating_profit")),
            _nested(data, "operating_profit", "margin_yoy_pp"),
        ),
        (
            "net_profit.margin_yoy_pp",
            net_profit,
            _num(prior.get("net_profit")),
            _nested(data, "net_profit", "margin_yoy_pp"),
        ),
        (
            "opex.rd_yoy_pp",
            rd,
            _nested(prior, "opex", "rd"),
            _nested(data, "opex", "rd_yoy_pp"),
        ),
        (
            "opex.sga_yoy_pp",
            sga,
            _nested(prior, "opex", "sga"),
            _nested(data, "opex", "sga_yoy_pp"),
        ),
    )
    for path, current, previous, reported in margin_checks:
        if current is None or previous is None or prior_revenue is None or reported is None:
            errors.append(f"missing values required to verify {path}")
            continue
        expected = (current / revenue - previous / prior_revenue) * 100
        if abs(expected - reported) > yoy_tol:
            errors.append(f"{path} is {reported:.2f}, expected {expected:.2f}")

    source_records = data.get("source_records") or []
    if not source_records:
        errors.append("source_records must include at least one source")
    else:
        for index, record in enumerate(source_records):
            if not isinstance(record, dict):
                errors.append(f"source_records[{index}] must be an object")
                continue
            errors.extend(_validate_source_record(record, index))
        if not any(
            str(record.get("type") or "").lower() in OFFICIAL_SOURCE_TYPES
            for record in source_records
            if isinstance(record, dict)
        ):
            errors.append("source_records must include an official or regulatory source")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_json", type=Path)
    parser.add_argument("--tolerance", type=float)
    args = parser.parse_args()

    data = json.loads(args.data_json.read_text())
    errors = validate(data, args.tolerance)
    if errors:
        print("INVALID", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        raise SystemExit(1)
    print("VALID")


if __name__ == "__main__":
    main()
