#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "matplotlib>=3.8",
#     "pillow>=10",
# ]
# ///
"""Render a 2000x1122 reference-layout income-statement Sankey PNG."""

from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgba
from matplotlib.path import Path as MplPath

WIDTH = 2000
HEIGHT = 1122

BG = "#F4F4F4"
TITLE = "#15577A"
DARK = "#050505"
GRAY = "#929292"
MUTED = "#5F5F5F"
GREEN = "#009447"
GREEN_BAR = "#27AA27"
GREEN_FLOW = "#A4CFA0"
RED = "#9D0800"
RED_BAR = "#E00000"
RED_FLOW = "#E9958D"
SOURCE = "#15577A"
_FONT_DPI = 100


def _money(value: float | None, unit: str, expense: bool = False) -> str:
    if value is None:
        return "n/a"
    amount = abs(float(value))
    precision = 2 if unit.upper() == "B" and 0 < amount < 0.1 else 1
    text = f"${amount:.{precision}f}{unit}"
    return f"({text})" if expense or float(value) < 0 else text


def _yoy(value: float | None) -> str:
    if value is None:
        return ""
    return f"({abs(value):.0f}%) Y/Y" if value < 0 else f"+{value:.0f}% Y/Y"


def _pp(value: float | None) -> str:
    if value is None:
        return ""
    if value < 0:
        return f"({abs(value):.0f}pp) Y/Y"
    if abs(value) < 0.05:
        return "(0pp) Y/Y"
    return f"+{value:.0f}pp Y/Y"


def _percent(value: float | None, suffix: str = "") -> str:
    if value is None:
        return ""
    return f"{float(value):.0f}%{suffix}"


def _bar(ax, x: float, y: float, width: float, height: float, color: str) -> None:
    if height <= 0:
        return
    ax.add_patch(
        patches.Rectangle(
            (x, y), width, height, facecolor=color, edgecolor="none", zorder=8
        )
    )


def _ribbon(
    ax,
    x0: float,
    top0: float,
    bottom0: float,
    x1: float,
    top1: float,
    bottom1: float,
    color: str,
    alpha: float = 0.92,
) -> None:
    dx = x1 - x0
    c1 = x0 + dx * 0.42
    c2 = x0 + dx * 0.58
    vertices = [
        (x0, top0),
        (c1, top0),
        (c2, top1),
        (x1, top1),
        (x1, bottom1),
        (c2, bottom1),
        (c1, bottom0),
        (x0, bottom0),
        (x0, top0),
    ]
    codes = [
        MplPath.MOVETO,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.LINETO,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.CLOSEPOLY,
    ]
    ax.add_patch(
        patches.PathPatch(
            MplPath(vertices, codes),
            facecolor=color,
            edgecolor="none",
            alpha=alpha,
            zorder=2,
        )
    )


def _bounded_stacked_spans(
    parent_top: float, parent_bottom: float, requested_heights: list[float]
) -> list[tuple[float, float]]:
    available = max(parent_bottom - parent_top, 0.0)
    heights = [max(float(requested), 0.0) for requested in requested_heights]
    requested_total = sum(heights)
    if requested_total > available and requested_total > 0:
        factor = available / requested_total
        heights = [requested * factor for requested in heights]

    spans: list[tuple[float, float]] = []
    cursor = parent_top
    for requested in heights:
        span_bottom = min(cursor + requested, parent_bottom)
        spans.append((cursor, span_bottom))
        cursor = span_bottom
    return spans


def _right_profit_layout(
    *,
    net_height: float,
    tax_height: float,
    operating_bottom: float,
    opex_top: float,
    opex_bottom: float,
    other_height: float,
    other_bar_width: float,
    net_is_loss: bool,
    other_inflow: bool,
) -> dict[str, float | bool]:
    if net_is_loss:
        net_top = 280.0
        tax_top = net_top + net_height + 20.0
    else:
        net_top = 310.0
        if tax_height > 0:
            net_top = min(
                net_top,
                max(245.0, 640.0 - tax_height - 20.0 - net_height),
            )
        tax_top = max(net_top + net_height + 20.0, net_top + 170.0)

    opex_label_in_gap = opex_top - operating_bottom >= 104.0
    opex_label_top = (
        operating_bottom + 12.0 if opex_label_in_gap else opex_bottom + 28.0
    )

    other_source_top = opex_bottom + 28.0
    if other_inflow:
        other_source_top = max(
            other_source_top,
            min(720.0, 1005.0 - other_height),
        )

    return {
        "net_top": net_top,
        "tax_top": tax_top,
        "opex_label_top": opex_label_top,
        "opex_label_in_gap": opex_label_in_gap,
        "other_source_top": other_source_top,
        "other_label_inside": (
            other_inflow and other_height >= 90.0 and other_bar_width >= 120.0
        ),
        "expense_start": max(615.0, tax_top + tax_height + 60.0),
    }


def _font(size: float, weight: str = "normal") -> dict[str, Any]:
    return {
        "fontsize": size * 100 / _FONT_DPI,
        "fontweight": weight,
        "fontfamily": "sans-serif",
    }


def _draw_image(
    ax,
    image_path: str | None,
    center_x: float,
    center_y: float,
    max_width: float,
    max_height: float,
    monochrome_color: str | None = None,
) -> bool:
    if not image_path:
        return False
    path = Path(image_path).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    if not path.exists():
        return False
    image = mpimg.imread(path)
    if monochrome_color and image.ndim == 3 and image.shape[2] >= 3:
        rgb = image[:, :, :3]
        luminance = rgb.mean(axis=2)
        alpha = np.clip((0.92 - luminance) / 0.12, 0.0, 1.0)
        if image.shape[2] == 4:
            alpha *= image[:, :, 3]
        color = to_rgba(monochrome_color)
        tinted = np.empty((*image.shape[:2], 4), dtype=float)
        tinted[:, :, :3] = color[:3]
        tinted[:, :, 3] = alpha
        image = tinted
    height, width = image.shape[:2]
    scale = min(max_width / width, max_height / height)
    draw_width = width * scale
    draw_height = height * scale
    ax.imshow(
        image,
        extent=(
            center_x - draw_width / 2,
            center_x + draw_width / 2,
            center_y + draw_height / 2,
            center_y - draw_height / 2,
        ),
        zorder=15,
    )
    return True


def _groups(data: dict[str, Any], revenue: float) -> list[dict[str, Any]]:
    configured = data.get("revenue_groups") or []
    groups: list[dict[str, Any]] = []
    for index, item in enumerate(configured):
        if item.get("revenue") is None:
            continue
        groups.append(
            {
                "id": str(item.get("id") or item.get("name") or f"group-{index}"),
                "name": str(item.get("name") or item.get("id") or f"Group {index + 1}"),
                "revenue": float(item["revenue"]),
                "yoy_pct": item.get("yoy_pct"),
            }
        )
    if groups:
        return groups

    products = data.get("products") or {}
    services = data.get("services") or {}
    if products.get("revenue") is not None:
        groups.append(
            {
                "id": "products",
                "name": "Products",
                "revenue": float(products["revenue"]),
                "yoy_pct": products.get("yoy_pct"),
            }
        )
    if services.get("revenue") is not None:
        groups.append(
            {
                "id": "services",
                "name": "Services",
                "revenue": float(services["revenue"]),
                "yoy_pct": services.get("yoy_pct"),
            }
        )
    if not groups:
        groups.append(
            {
                "id": "revenue",
                "name": "Revenue",
                "revenue": revenue,
                "yoy_pct": (data.get("total_revenue") or {}).get("yoy_pct"),
            }
        )
    return groups


def _source_label(data: dict[str, Any]) -> str:
    labels: list[str] = []
    for record in data.get("source_records") or []:
        label = str(record.get("label") or "").strip()
        if label and label not in labels:
            labels.append(label)
    if not labels:
        labels = [str(item) for item in data.get("source_notes") or [] if str(item)]
    text = " | ".join(labels[:2]) or "Official company filing"
    note = str(data.get("footer_note") or "").strip()
    return f"{text} | {note}" if note else text


def _figure(dpi: int):
    """Create the standard 2000x1122 canvas with an inverted-y pixel axis."""
    plt.rcParams["font.sans-serif"] = [
        "Helvetica Neue",
        "Helvetica",
        "Arial",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    fig = plt.figure(figsize=(WIDTH / dpi, HEIGHT / dpi), dpi=dpi, facecolor=BG)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, WIDTH)
    ax.set_ylim(HEIGHT, 0)
    ax.axis("off")
    ax.set_facecolor(BG)
    return fig, ax


def _title_block(fig, ax, data: dict[str, Any]) -> None:
    company = str(data.get("company") or data.get("ticker") or "Company")
    period = str(data.get("period_label") or "")
    period_end = str(data.get("period_end_label") or "")
    title_text = ax.text(
        1000,
        105,
        f"{company} {period} Income Statement",
        ha="center",
        va="center",
        color=TITLE,
        **_font(65, "bold"),
    )
    fig.canvas.draw()
    extent = title_text.get_window_extent(fig.canvas.get_renderer())
    if extent.width > 1860.0:
        title_text.set_fontsize(title_text.get_fontsize() * 1860.0 / extent.width)
    ax.text(1902, 190, period, ha="right", va="center", color="#444444", **_font(26, "bold"))
    ax.text(1902, 228, period_end, ha="right", va="center", color=MUTED, **_font(17))


def _footer_block(ax, data: dict[str, Any]) -> None:
    ax.text(1000, 1066, _source_label(data), ha="center", color=SOURCE, **_font(13, "bold"))
    ax.text(
        1000,
        1094,
        "For information only, not investment advice",
        ha="center",
        color=MUTED,
        **_font(10),
    )


def _render_conglomerate(data: dict[str, Any], out_path: Path, dpi: int = 100) -> Path:
    """Segment-basis layout for conglomerates and financials.

    Revenue splits straight into operating profit and operating costs (no
    gross-profit line, which is meaningless for insurers and holding
    companies), then operating profit plus non-operating inflows feed a
    pre-tax node that splits into net profit and tax.
    """
    global _FONT_DPI
    _FONT_DPI = dpi

    unit = str(data.get("unit") or "B")
    ticker = str(data.get("ticker") or "")
    company = str(data.get("company") or ticker or "Company")

    revenue = float(data["total_revenue"]["revenue"])
    revenue_yoy = (data.get("total_revenue") or {}).get("yoy_pct")

    operating = data.get("operating_profit") or {}
    operating_value = float(operating.get("amount") or 0)
    costs = data.get("operating_costs") or {}
    costs_value = float(costs.get("amount") or max(revenue - operating_value, 0))
    pretax = data.get("pretax_profit") or {}
    invest = data.get("investment_gains") or {}
    invest_value = float(invest.get("amount") or 0)
    other_value = float(data.get("other_income") or 0)
    pretax_value = float(
        pretax.get("amount") or operating_value + invest_value + other_value
    )
    net = data.get("net_profit") or {}
    net_value = float(net.get("amount") or 0)
    tax_value = float(data.get("tax") or 0)

    revenue_other = data.get("revenue_other") or {}
    revenue_other_value = float(revenue_other.get("amount") or 0)

    fig, ax = _figure(dpi)
    _title_block(fig, ax, data)

    scale = 330.0 / revenue

    def height(value: float | None, minimum: float = 0.0) -> float:
        if value is None:
            return minimum
        return max(abs(float(value)) * scale, minimum)

    x_segment, segment_width = 300.0, 54.0
    x_revenue, revenue_width = 700.0, 56.0
    x_split, split_width = 1030.0, 56.0
    x_pretax, pretax_width = 1350.0, 56.0
    x_final, final_width = 1670.0, 56.0

    revenue_height = height(revenue)
    revenue_top = 372.0
    revenue_bottom = revenue_top + revenue_height
    _bar(ax, x_revenue, revenue_top, revenue_width, revenue_height, DARK)

    brand = data.get("brand") or {}
    if not _draw_image(
        ax,
        brand.get("logo_path"),
        x_revenue + revenue_width / 2,
        205,
        260,
        120,
        brand.get("logo_color"),
    ):
        ax.text(
            x_revenue + revenue_width / 2,
            205,
            str(brand.get("logo_text") or ticker or company[:3].upper()),
            ha="center",
            va="center",
            color=DARK,
            **_font(38, "bold"),
        )
    ax.text(
        x_revenue + revenue_width / 2,
        revenue_top - 84,
        "Revenue",
        ha="center",
        va="center",
        color=DARK,
        **_font(25, "bold"),
    )
    ax.text(
        x_revenue + revenue_width / 2,
        revenue_top - 46,
        _money(revenue, unit),
        ha="center",
        va="center",
        color=DARK,
        **_font(24),
    )
    ax.text(
        x_revenue + revenue_width / 2,
        revenue_top - 12,
        _yoy(revenue_yoy),
        ha="center",
        va="bottom",
        color=MUTED,
        **_font(16),
    )

    # ---- left column: business segments, each with its own margin ----
    segments = [
        segment
        for segment in data.get("segments") or []
        if segment.get("revenue") is not None
    ][:9]
    wrapped = [
        textwrap.fill(str(segment.get("name") or ""), width=20) for segment in segments
    ]
    bar_heights = [height(float(segment["revenue"]), 12) for segment in segments]

    def _label_block(index: int) -> float:
        lines = wrapped[index].count("\n") + 1
        has_margin = segments[index].get("margin_pct") is not None
        return 25.0 * lines + (49.0 if has_margin else 28.0)

    label_blocks = [_label_block(index) for index in range(len(segments))]
    label_pitches = [block + 30.0 for block in label_blocks]
    band_top, band_bottom = 236.0, 1040.0
    gap = 5.0
    reserve = 62.0 if revenue_other_value > 0 else 0.0
    slots = [max(bar, pitch) for bar, pitch in zip(bar_heights, label_pitches)]
    gaps = gap * max(len(slots) - 1, 0)
    available = band_bottom - band_top - reserve
    if sum(slots) + gaps > available:
        factor = max(0.5, (available - gaps) / max(sum(slots), 1.0))
        slots = [
            max(bar, pitch * factor) for bar, pitch in zip(bar_heights, label_pitches)
        ]
    cursor = band_top + max(0.0, (available - (sum(slots) + gaps)) / 2)
    target_cursor = revenue_top
    for index, segment in enumerate(segments):
        value = float(segment["revenue"])
        slot = slots[index]
        bar_height = bar_heights[index]
        center = cursor + slot / 2
        cursor += slot + gap
        bar_top = center - bar_height / 2
        target_height = revenue_height * value / revenue
        _bar(ax, x_segment, bar_top, segment_width, bar_height, DARK)
        _ribbon(
            ax,
            x_segment + segment_width,
            bar_top,
            bar_top + bar_height,
            x_revenue,
            target_cursor,
            target_cursor + target_height,
            GRAY,
            0.93,
        )
        target_cursor += target_height

        margin_pct = segment.get("margin_pct")
        block = label_blocks[index]
        name_lines = wrapped[index].count("\n") + 1
        _draw_image(ax, segment.get("icon_path"), 120, center, 74, 62)
        icon_drawn = bool(segment.get("icon_path"))
        name_text = ax.text(
            x_segment - 42,
            center - block / 2,
            wrapped[index],
            ha="right",
            va="top",
            color=DARK,
            linespacing=0.95,
            **_font(19, "bold"),
        )
        left_limit = 172.0 if icon_drawn else 26.0
        name_extent = name_text.get_window_extent(fig.canvas.get_renderer())
        if name_extent.x0 < left_limit and name_extent.width > 0:
            name_text.set_fontsize(
                name_text.get_fontsize()
                * (x_segment - 42 - left_limit)
                / name_extent.width
            )
        detail = _money(value, unit)
        yoy_text = _yoy(segment.get("yoy_pct"))
        if yoy_text:
            detail = f"{detail}   {yoy_text}"
        ax.text(
            x_segment - 42,
            center - block / 2 + 25.0 * name_lines + 16,
            detail,
            ha="right",
            va="center",
            color=MUTED,
            **_font(15),
        )
        if margin_pct is not None:
            ax.text(
                x_segment - 42,
                center + block / 2 - 9,
                _percent(margin_pct, " margin"),
                ha="right",
                va="center",
                color=GREEN if float(margin_pct) >= 0 else RED,
                **_font(14, "bold"),
            )

    if revenue_other_value > 0:
        other_rev_height = height(revenue_other_value, 10)
        other_rev_top = min(cursor + 26.0, band_bottom - other_rev_height)
        _bar(ax, x_segment, other_rev_top, segment_width, other_rev_height, GREEN_BAR)
        _ribbon(
            ax,
            x_segment + segment_width,
            other_rev_top,
            other_rev_top + height(revenue_other_value),
            x_revenue,
            target_cursor,
            revenue_bottom,
            GREEN_FLOW,
        )
        label = str(revenue_other.get("name") or "Other")
        ax.text(
            x_segment - 42,
            other_rev_top + other_rev_height / 2 - 12,
            label,
            ha="right",
            va="center",
            color=GREEN,
            **_font(18, "bold"),
        )
        ax.text(
            x_segment - 42,
            other_rev_top + other_rev_height / 2 + 14,
            _money(revenue_other_value, unit),
            ha="right",
            va="center",
            color=GREEN,
            **_font(15),
        )

    # ---- revenue -> operating profit + operating costs ----
    operating_height = height(operating_value)
    costs_height = height(costs_value)
    invest_height = height(invest_value, 10)
    other_height = height(other_value, 10)
    operating_top = 330.0
    invest_top = operating_top + operating_height + 62.0
    other_top = invest_top + invest_height + 84.0
    costs_top = other_top + other_height + 40.0
    if costs_top + costs_height > 995.0:
        costs_top = max(other_top + other_height + 16.0, 995.0 - costs_height)
    _ribbon(
        ax,
        x_revenue + revenue_width,
        revenue_top,
        revenue_top + operating_height,
        x_split,
        operating_top,
        operating_top + operating_height,
        GREEN_FLOW,
    )
    _ribbon(
        ax,
        x_revenue + revenue_width,
        revenue_top + operating_height,
        revenue_bottom,
        x_split,
        costs_top,
        costs_top + costs_height,
        RED_FLOW,
    )
    _bar(ax, x_split, operating_top, split_width, operating_height, GREEN_BAR)
    _bar(ax, x_split, costs_top, split_width, costs_height, RED_BAR)

    ax.text(
        x_split + split_width / 2,
        operating_top - 96,
        "Operating profit",
        ha="center",
        color=GREEN,
        **_font(23, "bold"),
    )
    ax.text(
        x_split + split_width / 2,
        operating_top - 58,
        _money(operating_value, unit),
        ha="center",
        color=GREEN,
        **_font(21),
    )
    ax.text(
        x_split + split_width / 2,
        operating_top - 24,
        _percent(operating.get("margin_pct"), " margin"),
        ha="center",
        color=MUTED,
        **_font(15),
    )
    if operating.get("margin_yoy_pp") is not None:
        ax.text(
            x_split + split_width / 2,
            operating_top - 2,
            _pp(operating.get("margin_yoy_pp")),
            ha="center",
            va="bottom",
            color=MUTED,
            **_font(14),
        )
    costs_label_y = costs_top + costs_height + 34
    ax.text(
        x_split + split_width / 2,
        costs_label_y,
        "Operating costs",
        ha="center",
        color=RED,
        **_font(19, "bold"),
    )
    ax.text(
        x_split + split_width / 2,
        costs_label_y + 32,
        "and expenses",
        ha="center",
        color=RED,
        **_font(19, "bold"),
    )
    ax.text(
        x_split + split_width / 2,
        costs_label_y + 66,
        _money(costs_value, unit, True),
        ha="center",
        color=RED,
        **_font(18),
    )

    # ---- operating profit + investment gains + other -> pre-tax ----
    pretax_height = height(pretax_value)
    pretax_top = 300.0

    _bar(ax, x_split, invest_top, split_width, invest_height, GREEN_BAR)
    if abs(other_value) > 0.05:
        _bar(ax, x_split, other_top, split_width, other_height, GREEN_BAR)

    inflow_cursor = pretax_top
    for source_top, source_value, flow_color in (
        (operating_top, operating_value, GREEN_FLOW),
        (invest_top, invest_value, GREEN_FLOW),
        (other_top, other_value, GREEN_FLOW),
    ):
        thickness = height(source_value)
        if thickness <= 0.5:
            continue
        _ribbon(
            ax,
            x_split + split_width,
            source_top,
            source_top + thickness,
            x_pretax,
            inflow_cursor,
            inflow_cursor + thickness,
            flow_color,
        )
        inflow_cursor += thickness
    _bar(ax, x_pretax, pretax_top, pretax_width, pretax_height, GREEN_BAR)

    ax.text(
        x_split + split_width / 2,
        invest_top + invest_height + 28,
        "Investment gains",
        ha="center",
        color=GREEN,
        **_font(18, "bold"),
    )
    ax.text(
        x_split + split_width / 2,
        invest_top + invest_height + 58,
        _money(invest_value, unit),
        ha="center",
        color=GREEN,
        **_font(16),
    )
    if abs(other_value) > 0.05:
        ax.text(
            x_split + split_width / 2 + 132,
            other_top + other_height / 2 - 14,
            "Other",
            ha="center",
            color=GREEN,
            **_font(17, "bold"),
        )
        ax.text(
            x_split + split_width / 2 + 132,
            other_top + other_height / 2 + 14,
            _money(other_value, unit),
            ha="center",
            color=GREEN,
            **_font(15),
        )

    pretax_label = str(pretax.get("label") or "Profit before tax")
    ax.text(
        x_pretax + pretax_width / 2,
        pretax_top - 72,
        pretax_label,
        ha="center",
        color=GREEN,
        **_font(21, "bold"),
    )
    ax.text(
        x_pretax + pretax_width / 2,
        pretax_top - 36,
        _money(pretax_value, unit),
        ha="center",
        color=GREEN,
        **_font(20),
    )

    # ---- pre-tax -> net profit + tax ----
    net_height = height(net_value)
    tax_height = height(tax_value, 10) if tax_value > 0 else 0.0
    net_top = 262.0
    tax_top = net_top + net_height + 92.0
    outflow_cursor = pretax_top
    _ribbon(
        ax,
        x_pretax + pretax_width,
        outflow_cursor,
        outflow_cursor + net_height,
        x_final,
        net_top,
        net_top + net_height,
        GREEN_FLOW,
    )
    outflow_cursor += net_height
    _bar(ax, x_final, net_top, final_width, net_height, GREEN_BAR)
    if tax_height > 0:
        _ribbon(
            ax,
            x_pretax + pretax_width,
            outflow_cursor,
            outflow_cursor + height(tax_value),
            x_final,
            tax_top,
            tax_top + tax_height,
            RED_FLOW,
        )
        _bar(ax, x_final, tax_top, final_width, tax_height, RED_BAR)

    ax.text(
        x_final + final_width + 22,
        net_top + 18,
        "Net profit",
        ha="left",
        color=GREEN,
        **_font(22, "bold"),
    )
    ax.text(
        x_final + final_width + 22,
        net_top + 56,
        _money(net_value, unit),
        ha="left",
        color=GREEN,
        **_font(20),
    )
    ax.text(
        x_final + final_width + 22,
        net_top + 90,
        _percent(net.get("margin_pct"), " margin"),
        ha="left",
        color=MUTED,
        **_font(15),
    )
    if net.get("margin_yoy_pp") is not None:
        ax.text(
            x_final + final_width + 22,
            net_top + 120,
            _pp(net.get("margin_yoy_pp")),
            ha="left",
            color=MUTED,
            **_font(14),
        )
    if tax_height > 0:
        ax.text(
            x_final + final_width + 22,
            tax_top + 12,
            "Tax",
            ha="left",
            color=RED,
            **_font(19, "bold"),
        )
        ax.text(
            x_final + final_width + 22,
            tax_top + 46,
            _money(tax_value, unit, True),
            ha="left",
            color=RED,
            **_font(16),
        )

    _footer_block(ax, data)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, facecolor=BG)
    plt.close(fig)
    return out_path


def render(data: dict[str, Any], out_path: Path, dpi: int = 100) -> Path:
    if str((data.get("layout") or {}).get("style") or "").lower() == "conglomerate":
        return _render_conglomerate(data, out_path, dpi=dpi)
    global _FONT_DPI
    _FONT_DPI = dpi

    unit = str(data.get("unit") or "B")
    company = str(data.get("company") or data.get("ticker") or "Company")
    ticker = str(data.get("ticker") or "")
    period = str(data.get("period_label") or "")
    period_end = str(data.get("period_end_label") or "")

    total = data["total_revenue"]
    revenue = float(total["revenue"])
    revenue_yoy = total.get("yoy_pct")
    scale = 2.92 * 109.4 / revenue

    def height(value: float | None, minimum: float = 0.0) -> float:
        if value is None:
            return minimum
        return max(abs(float(value)) * scale, minimum)

    gross = data.get("gross_profit") or {}
    cogs = data.get("cogs") or {}
    operating = data.get("operating_profit") or {}
    opex = data.get("opex") or {}
    net = data.get("net_profit") or {}
    gross_value = float(gross.get("amount") or 0)
    cogs_value = float(cogs.get("amount") or max(revenue - gross_value, 0))
    operating_value = float(operating.get("amount") or 0)
    opex_value = float(opex.get("amount") or max(gross_value - operating_value, 0))
    net_value = float(net.get("amount") or 0)
    tax_value = float(data.get("tax") or 0)
    other_value = float(data.get("other_income") or 0)
    rd_value = float(opex.get("rd") or 0)
    sga_value = float(opex.get("sga") or 0)

    plt.rcParams["font.sans-serif"] = [
        "Helvetica Neue",
        "Helvetica",
        "Arial",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    fig = plt.figure(figsize=(WIDTH / dpi, HEIGHT / dpi), dpi=dpi, facecolor=BG)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, WIDTH)
    ax.set_ylim(HEIGHT, 0)
    ax.axis("off")
    ax.set_facecolor(BG)

    title_text = ax.text(
        1000,
        105,
        f"{company} {period} Income Statement",
        ha="center",
        va="center",
        color=TITLE,
        **_font(65, "bold"),
    )
    fig.canvas.draw()
    title_extent = title_text.get_window_extent(fig.canvas.get_renderer())
    if title_extent.width > 1860.0:
        title_text.set_fontsize(
            title_text.get_fontsize() * 1860.0 / title_extent.width
        )
    ax.text(1902, 190, period, ha="right", va="center", color="#444444", **_font(26, "bold"))
    ax.text(1902, 228, period_end, ha="right", va="center", color=MUTED, **_font(17))

    x_segment, segment_width = 290.0, 54.0
    x_group, group_width = 570.0, 55.0
    x_revenue, revenue_width = 850.0, 56.0
    x_gross, split_width = 1132.0, 56.0
    x_cost_detail, detail_width = 1290.0, 50.0
    x_operating, operating_width = 1412.0, 55.0
    x_final, final_width = 1692.0, 55.0

    revenue_top = 510.0
    revenue_height = height(revenue)
    revenue_bottom = revenue_top + revenue_height
    _bar(ax, x_revenue, revenue_top, revenue_width, revenue_height, DARK)

    brand = data.get("brand") or {}
    logo_path = brand.get("logo_path")
    logo_drawn = _draw_image(
        ax,
        logo_path,
        x_revenue + revenue_width / 2,
        292,
        270,
        235,
        brand.get("logo_color"),
    )
    if not logo_drawn:
        logo_text = str(brand.get("logo_text") or ticker or company[:3].upper())
        ax.text(
            x_revenue + revenue_width / 2,
            286,
            logo_text,
            ha="center",
            va="center",
            color=DARK,
            **_font(42, "bold"),
        )
    ax.text(
        x_revenue + revenue_width / 2,
        revenue_top - 92,
        "Revenue",
        ha="center",
        va="center",
        color=DARK,
        **_font(25, "bold"),
    )
    ax.text(
        x_revenue + revenue_width / 2,
        revenue_top - 52,
        _money(revenue, unit),
        ha="center",
        va="center",
        color=DARK,
        **_font(24),
    )
    ax.text(
        x_revenue + revenue_width / 2,
        revenue_top - 14,
        _yoy(revenue_yoy),
        ha="center",
        va="bottom",
        color=MUTED,
        **_font(16),
    )

    groups = _groups(data, revenue)
    if len(groups) == 1:
        group_centers = [610.0]
    elif len(groups) == 2:
        group_centers = [550.0, 940.0]
    else:
        group_centers = [
            410.0 + i * (510.0 / (len(groups) - 1)) for i in range(len(groups))
        ]
    target_cursor = revenue_top
    group_geometry: dict[str, dict[str, float]] = {}
    for group_index, (group, center) in enumerate(zip(groups, group_centers)):
        group_height = height(group["revenue"], 12)
        group_top = center - group_height / 2
        group_bottom = center + group_height / 2
        target_height = revenue_height * group["revenue"] / revenue
        target_top = target_cursor
        target_bottom = target_top + target_height
        target_cursor = target_bottom
        group_geometry[group["id"]] = {
            "top": group_top,
            "bottom": group_bottom,
            "target_top": target_top,
            "target_bottom": target_bottom,
        }
        _bar(ax, x_group, group_top, group_width, group_height, DARK)
        _ribbon(
            ax,
            x_group + group_width,
            group_top,
            group_bottom,
            x_revenue,
            target_top,
            target_bottom,
            GRAY,
            0.93,
        )
        if len(groups) == 2:
            label_y = min(330.0 if group_index == 0 else 790.0, group_top - 96.0)
            label_x = x_group + group_width / 2
            label_ha = "center"
            amount_y = label_y + 43.0
            yoy_y = label_y + 80.0
        else:
            label_y = center - 38.0
            label_x = x_group - 14.0
            label_ha = "right"
            amount_y = center + 3.0
            yoy_y = center + 39.0
        ax.text(
            label_x,
            label_y,
            group["name"],
            ha=label_ha,
            va="center",
            color=DARK,
            **_font(20 if len(groups) > 2 else 22, "bold"),
        )
        ax.text(
            label_x,
            amount_y,
            _money(group["revenue"], unit),
            ha=label_ha,
            va="center",
            color=DARK,
            **_font(19 if len(groups) > 2 else 21),
        )
        ax.text(
            label_x,
            yoy_y,
            _yoy(group.get("yoy_pct")),
            ha=label_ha,
            va="center",
            color=MUTED,
            **_font(15),
        )

    segments = [
        segment
        for segment in data.get("segments") or []
        if segment.get("revenue") is not None
    ][:8]
    compact_segments = len(segments) > 6
    compact_wrapped = (
        [
            textwrap.fill(str(segment.get("name") or ""), width=20)
            for segment in segments
        ]
        if compact_segments
        else []
    )
    if segments:
        if len(segments) == 1:
            centers = [485.0]
        elif len(segments) == 4:
            centers = [390.0, 580.0, 710.0, 805.0]
        elif compact_segments:
            band_top, band_bottom = 285.0, 1010.0
            slot_gap = 4.0
            raw_heights = [
                height(float(segment["revenue"]), 13) for segment in segments
            ]
            label_pitches = [
                21.0 * (text.count("\n") + 1) + 44.0 for text in compact_wrapped
            ]
            available = band_bottom - band_top
            slots = [
                max(bar, pitch) for bar, pitch in zip(raw_heights, label_pitches)
            ]
            gaps = slot_gap * (len(slots) - 1)
            if sum(slots) + gaps > available:
                factor = max(
                    0.55, (available - gaps) / max(sum(slots), 1.0)
                )
                slots = [
                    max(bar, pitch * factor)
                    for bar, pitch in zip(raw_heights, label_pitches)
                ]
            cursor = band_top + max(
                0.0, (available - (sum(slots) + gaps)) / 2
            )
            centers = []
            for slot in slots:
                centers.append(cursor + slot / 2)
                cursor += slot + slot_gap
        else:
            centers = [
                340.0 + i * (500.0 / (len(segments) - 1))
                for i in range(len(segments))
            ]
        segment_cursors = {
            group_id: geometry["top"] for group_id, geometry in group_geometry.items()
        }
        for index, (segment, center) in enumerate(zip(segments, centers)):
            value = float(segment["revenue"])
            segment_height = height(value, 13)
            segment_top = center - segment_height / 2
            segment_bottom = center + segment_height / 2
            group_id = str(segment.get("group") or groups[0]["id"])
            if group_id not in group_geometry:
                group_id = groups[0]["id"]
            geometry = group_geometry[group_id]
            group_value = next(
                group["revenue"] for group in groups if group["id"] == group_id
            )
            target_height = (
                (geometry["bottom"] - geometry["top"]) * value / group_value
                if group_value
                else segment_height
            )
            target_top = segment_cursors[group_id]
            target_bottom = min(target_top + target_height, geometry["bottom"])
            segment_cursors[group_id] = target_bottom
            _bar(ax, x_segment, segment_top, segment_width, segment_height, DARK)
            _ribbon(
                ax,
                x_segment + segment_width,
                segment_top,
                segment_bottom,
                x_group,
                target_top,
                target_bottom,
                GRAY,
                0.93,
            )

            icon_drawn = _draw_image(
                ax,
                segment.get("icon_path"),
                115,
                center,
                70,
                70,
            )
            if compact_segments and not icon_drawn:
                detail = _money(value, unit)
                yoy_text = _yoy(segment.get("yoy_pct"))
                if yoy_text:
                    detail = f"{detail}   {yoy_text}"
                wrapped = compact_wrapped[index]
                block = 21.0 * (wrapped.count("\n") + 1) + 32.0
                name_text = ax.text(
                    255,
                    center - block / 2,
                    wrapped,
                    ha="right",
                    va="top",
                    color=DARK,
                    linespacing=0.95,
                    **_font(16, "bold"),
                )
                name_extent = name_text.get_window_extent(fig.canvas.get_renderer())
                if name_extent.x0 < 10.0 and name_extent.width > 0:
                    name_text.set_fontsize(
                        name_text.get_fontsize() * 245.0 / name_extent.width
                    )
                ax.text(
                    255,
                    center + block / 2 - 9,
                    detail,
                    ha="right",
                    va="center",
                    color=MUTED,
                    **_font(14),
                )
                continue
            label_x = 255
            ha = "right"
            if not icon_drawn:
                segment_name = str(segment.get("name") or "")
                wrapped_name = (
                    textwrap.fill(segment_name, width=18)
                    if len(segment_name) > 20
                    else segment_name
                )
                ax.text(
                    label_x,
                    center,
                    wrapped_name,
                    ha=ha,
                    va="center",
                    color=DARK,
                    linespacing=0.95,
                    **_font(22 if len(segments) <= 4 else 19, "bold"),
                )
                subtitle = str(segment.get("subtitle") or "")
                if subtitle:
                    long_subtitle = len(subtitle) > 22
                    ax.text(
                        160 if long_subtitle else label_x,
                        center + 22,
                        textwrap.fill(subtitle, width=22),
                        ha="center" if long_subtitle else ha,
                        va="top",
                        color=MUTED,
                        linespacing=0.95,
                        **_font(11 if long_subtitle else 12),
                    )
            else:
                ax.text(
                    155,
                    center,
                    str(segment.get("name") or ""),
                    ha="left",
                    va="center",
                    color=DARK,
                    **_font(22, "bold"),
                )
            amount_y = segment_top - (36 if index == len(segments) - 1 else 64)
            ax.text(
                x_segment - 20,
                amount_y,
                _money(value, unit),
                ha="right",
                va="center",
                color=DARK,
                **_font(19),
            )
            ax.text(
                x_segment - 20,
                amount_y + 34,
                _yoy(segment.get("yoy_pct")),
                ha="right",
                va="center",
                color=MUTED,
                **_font(14),
            )

    gross_height = height(gross_value)
    cogs_height = height(cogs_value)
    gross_top = 434.0
    gross_bottom = gross_top + gross_height
    cogs_top = 772.0
    cogs_bottom = cogs_top + cogs_height
    _ribbon(
        ax,
        x_revenue + revenue_width,
        revenue_top,
        revenue_top + gross_height,
        x_gross,
        gross_top,
        gross_bottom,
        GREEN_FLOW,
    )
    _ribbon(
        ax,
        x_revenue + revenue_width,
        revenue_top + gross_height,
        revenue_bottom,
        x_gross,
        cogs_top,
        cogs_bottom,
        RED_FLOW,
    )
    _bar(ax, x_gross, gross_top, split_width, gross_height, GREEN_BAR)
    _bar(ax, x_gross, cogs_top, split_width, cogs_height, RED_BAR)

    ax.text(1158, 302, "Gross profit", ha="center", color=GREEN, **_font(24, "bold"))
    ax.text(1158, 343, _money(gross_value, unit), ha="center", color=GREEN, **_font(21))
    ax.text(
        1158,
        378,
        _percent(gross.get("margin_pct"), " margin"),
        ha="center",
        color=MUTED,
        **_font(15),
    )
    ax.text(
        1158,
        409,
        _pp(gross.get("margin_yoy_pp")),
        ha="center",
        color=MUTED,
        **_font(14),
    )

    operating_height = height(operating_value)
    opex_height = height(opex_value)
    operating_top = 365.0
    operating_bottom = operating_top + operating_height
    opex_top = 590.0
    opex_bottom = opex_top + opex_height
    _ribbon(
        ax,
        x_gross + split_width,
        gross_top,
        gross_top + operating_height,
        x_operating,
        operating_top,
        operating_bottom,
        GREEN_FLOW,
    )
    _ribbon(
        ax,
        x_gross + split_width,
        gross_top + operating_height,
        gross_bottom,
        x_operating,
        opex_top,
        opex_bottom,
        RED_FLOW,
    )
    _bar(ax, x_operating, operating_top, operating_width, operating_height, GREEN_BAR)
    _bar(ax, x_operating, opex_top, operating_width, opex_height, RED_BAR)

    ax.text(1438, 236, "Operating profit", ha="center", color=GREEN, **_font(23, "bold"))
    ax.text(1438, 277, _money(operating_value, unit), ha="center", color=GREEN, **_font(21))
    ax.text(
        1438,
        313,
        _percent(operating.get("margin_pct"), " margin"),
        ha="center",
        color=MUTED,
        **_font(15),
    )
    ax.text(
        1438,
        344,
        _pp(operating.get("margin_yoy_pp")),
        ha="center",
        color=MUTED,
        **_font(14),
    )
    cogs_parts: list[tuple[str, float, Any]] = []
    for part in cogs.get("parts") or []:
        if part.get("amount") is None:
            continue
        cogs_parts.append(
            (str(part.get("name") or ""), float(part["amount"]), part.get("gm_pct"))
        )
    if not cogs_parts:
        product_cogs = cogs.get("products")
        service_cogs = cogs.get("services")
        if product_cogs is not None:
            cogs_parts.append(
                ("Products", float(product_cogs), cogs.get("products_gm_pct"))
            )
        if service_cogs is not None:
            cogs_parts.append(
                ("Services", float(service_cogs), cogs.get("services_gm_pct"))
            )
    if cogs_parts:
        rendered_parts = cogs_parts[:2]
        source_spans = _bounded_stacked_spans(
            cogs_top,
            cogs_bottom,
            [height(value) for _, value, _ in rendered_parts],
        )
        part_tops = [790.0, 960.0]
        min_second_top = 790.0 + height(rendered_parts[0][1], 12) + 30.0
        if len(rendered_parts) > 1 and part_tops[1] < min_second_top:
            part_tops[1] = min_second_top
        for index, ((name, value, margin), source_span) in enumerate(
            zip(rendered_parts, source_spans)
        ):
            part_height = height(value, 12)
            part_top = part_tops[index]
            part_bottom = part_top + part_height
            _ribbon(
                ax,
                x_gross + split_width,
                source_span[0],
                source_span[1],
                x_cost_detail,
                part_top,
                part_bottom,
                RED_FLOW,
            )
            _bar(ax, x_cost_detail, part_top, detail_width, part_height, RED_BAR)
            text_y = part_top + 18.0 if index == 0 else part_top - 42.0
            ax.text(
                x_cost_detail + 150,
                text_y,
                name,
                ha="center",
                color=RED,
                **_font(17, "bold"),
            )
            ax.text(
                x_cost_detail + 150,
                text_y + 34,
                _money(value, unit, True),
                ha="center",
                color=RED,
                **_font(16),
            )
            if margin is not None:
                ax.text(
                    x_cost_detail + 150,
                    text_y + 67,
                    _percent(margin, " gross margin"),
                    ha="center",
                    color=MUTED,
                    **_font(14),
                )

    ax.text(1158, 676, "Cost of", ha="center", color=RED, **_font(19, "bold"))
    ax.text(1158, 708, "revenue", ha="center", color=RED, **_font(19, "bold"))
    ax.text(1158, 748, _money(cogs_value, unit, True), ha="center", color=RED, **_font(17))

    net_height = height(net_value)
    net_is_loss = net_value < 0
    tax_height = height(tax_value, 11) if tax_value > 0 else 0.0
    tax_accounting_height = height(tax_value) if tax_value > 0 else 0.0
    other_inflow = other_value > 0.05
    other_height = height(other_value, 10) if other_inflow else 0.0
    right_layout = _right_profit_layout(
        net_height=net_height,
        tax_height=tax_height,
        operating_bottom=operating_bottom,
        opex_top=opex_top,
        opex_bottom=opex_bottom,
        other_height=other_height,
        other_bar_width=operating_width,
        net_is_loss=net_is_loss,
        other_inflow=other_inflow,
    )
    net_top = float(right_layout["net_top"])
    net_bottom = net_top + net_height
    tax_top = float(right_layout["tax_top"])
    x_source = x_operating + operating_width

    opex_label_top = float(right_layout["opex_label_top"])
    ax.text(
        1440,
        opex_label_top,
        "Operating",
        ha="center",
        color=RED,
        **_font(19, "bold"),
    )
    ax.text(
        1440,
        opex_label_top + 32.0,
        "expenses",
        ha="center",
        color=RED,
        **_font(19, "bold"),
    )
    ax.text(
        1440,
        opex_label_top + 72.0,
        _money(opex_value, unit, True),
        ha="center",
        color=RED,
        **_font(18),
    )

    if net_is_loss:
        other_height = height(abs(other_value), 10)
        other_top = net_top
        x_other = x_source + (x_final - x_source) * 0.36
        other_width = 48.0
        offset_height = min(operating_height, other_height)
        remaining_top = other_top + offset_height

        _ribbon(
            ax,
            x_source,
            operating_top,
            operating_bottom,
            x_other,
            other_top,
            other_top + offset_height,
            GREEN_FLOW,
        )
        _bar(ax, x_other, other_top, other_width, other_height, RED_BAR)
        remaining_bottom = other_top + other_height
        tax_source_height = (
            min(tax_accounting_height, max(remaining_bottom - remaining_top, 0.0))
            if tax_height > 0
            else 0.0
        )
        tax_source_top = remaining_bottom - tax_source_height
        net_source_bottom = tax_source_top if tax_height > 0 else remaining_bottom
        _ribbon(
            ax,
            x_other + other_width,
            remaining_top,
            net_source_bottom,
            x_final,
            net_top,
            net_bottom,
            RED_FLOW,
        )
        if tax_height > 0:
            _ribbon(
                ax,
                x_other + other_width,
                tax_source_top,
                remaining_bottom,
                x_final,
                tax_top,
                tax_top + tax_height,
                RED_FLOW,
            )
        loss_flow_x = (x_other + other_width + x_final) / 2
        loss_flow_y = net_top + net_height / 2
        if net_height >= 90:
            ax.text(
                loss_flow_x,
                loss_flow_y - 28,
                "Other expense",
                ha="center",
                color="white",
                zorder=12,
                **_font(15, "bold"),
            )
            ax.text(
                loss_flow_x,
                loss_flow_y + 8,
                _money(other_value, unit, expense=True),
                ha="center",
                color="white",
                zorder=12,
                **_font(14),
            )
        else:
            ax.text(
                x_other + other_width / 2,
                other_top - 48,
                "Other expense",
                ha="center",
                color=RED,
                **_font(15, "bold"),
            )
            ax.text(
                x_other + other_width / 2,
                other_top - 18,
                _money(other_value, unit, expense=True),
                ha="center",
                color=RED,
                **_font(14),
            )
    elif other_inflow:
        # Positive non-operating income adds to profit, so route it as an
        # inflow that merges into net profit (matching the reference layout)
        # instead of an outflow leaving operating profit.
        other_source_top = float(right_layout["other_source_top"])
        _bar(
            ax,
            x_operating,
            other_source_top,
            operating_width,
            other_height,
            GREEN_BAR,
        )
        supplies = [
            [operating_top, operating_height],
            [other_source_top, height(other_value)],
        ]
        for sink_top, sink_height, accounting_height, sink_color in (
            (net_top, net_height, height(net_value), GREEN_FLOW),
            (tax_top, tax_height, tax_accounting_height, RED_FLOW),
        ):
            cursor = sink_top
            remaining = accounting_height
            for supply in supplies:
                if remaining <= 0:
                    break
                take = min(remaining, supply[1])
                if take <= 0:
                    continue
                target_take = (
                    sink_height * take / accounting_height
                    if accounting_height > 0
                    else 0.0
                )
                _ribbon(
                    ax,
                    x_source,
                    supply[0],
                    supply[0] + take,
                    x_final,
                    cursor,
                    cursor + target_take,
                    sink_color,
                )
                supply[0] += take
                supply[1] -= take
                cursor += target_take
                remaining -= take
        if right_layout["other_label_inside"]:
            other_center = other_source_top + other_height / 2
            ax.text(
                x_operating + operating_width / 2,
                other_center - 17,
                "Other income",
                ha="center",
                color="white",
                zorder=12,
                **_font(15, "bold"),
            )
            ax.text(
                x_operating + operating_width / 2,
                other_center + 18,
                _money(other_value, unit),
                ha="center",
                color="white",
                zorder=12,
                **_font(14),
            )
        elif other_height >= 90.0:
            other_center = other_source_top + other_height / 2
            ax.text(
                x_operating - 18,
                other_center - 17,
                "Other income",
                ha="right",
                color=GREEN,
                **_font(15, "bold"),
            )
            ax.text(
                x_operating - 18,
                other_center + 18,
                _money(other_value, unit),
                ha="right",
                color=GREEN,
                **_font(14),
            )
        else:
            ax.text(
                x_operating + operating_width / 2,
                other_source_top + other_height + 26,
                "Other",
                ha="center",
                color=GREEN,
                **_font(17, "bold"),
            )
            ax.text(
                x_operating + operating_width / 2,
                other_source_top + other_height + 58,
                _money(other_value, unit),
                ha="center",
                color=GREEN,
                **_font(15),
            )
    else:
        other_expense_height = (
            height(abs(other_value)) if other_value < -0.05 else 0.0
        )
        source_spans = _bounded_stacked_spans(
            operating_top,
            operating_bottom,
            [height(net_value), other_expense_height, tax_accounting_height],
        )
        _ribbon(
            ax,
            x_source,
            source_spans[0][0],
            source_spans[0][1],
            x_final,
            net_top,
            net_bottom,
            GREEN_FLOW,
        )
        if other_value < -0.05:
            other_height = height(abs(other_value), 10)
            other_top = 430.0
            _ribbon(
                ax,
                x_source,
                source_spans[1][0],
                source_spans[1][1],
                x_final,
                other_top,
                other_top + other_height,
                RED_FLOW,
            )
            _bar(ax, x_final, other_top, final_width, other_height, RED_BAR)
            ax.text(1640, 450, "Other", ha="center", color=RED, **_font(17, "bold"))
            ax.text(
                1640,
                482,
                _money(other_value, unit, expense=True),
                ha="center",
                color=RED,
                **_font(15),
            )
        if tax_height > 0:
            _ribbon(
                ax,
                x_source,
                source_spans[2][0],
                source_spans[2][1],
                x_final,
                tax_top,
                tax_top + tax_height,
                RED_FLOW,
            )

    net_bar_color = RED_BAR if net_is_loss else GREEN_BAR
    net_text_color = RED if net_is_loss else GREEN
    _bar(ax, x_final, net_top, final_width, net_height, net_bar_color)
    ax.text(
        1764,
        net_top + 25,
        "Net loss" if net_is_loss else "Net profit",
        ha="left",
        color=net_text_color,
        **_font(22, "bold"),
    )
    ax.text(
        1764,
        net_top + 65,
        _money(net_value, unit),
        ha="left",
        color=net_text_color,
        **_font(20),
    )
    ax.text(
        1764,
        net_top + 102,
        _percent(net.get("margin_pct"), " margin"),
        ha="left",
        color=MUTED,
        **_font(15),
    )
    ax.text(
        1764,
        net_top + 134,
        _pp(net.get("margin_yoy_pp")),
        ha="left",
        color=MUTED,
        **_font(14),
    )

    if tax_height > 0:
        _bar(ax, x_final, tax_top, final_width, tax_height, RED_BAR)
        ax.text(
            1816,
            tax_top - 5,
            "Tax",
            ha="center",
            color=RED,
            **_font(17, "bold"),
        )
        ax.text(
            1816,
            tax_top + 24,
            _money(tax_value, unit, True),
            ha="center",
            color=RED,
            **_font(15),
        )

    configured_expenses = [
        item for item in opex.get("items") or [] if item.get("amount") is not None
    ]
    expense_start = float(right_layout["expense_start"])
    expense_bottom = 1025.0
    show_expense_pp = True
    if configured_expenses:
        entries = [
            (
                str(item.get("name") or ""),
                float(item["amount"]),
                item.get("pct_rev"),
                item.get("yoy_pp"),
            )
            for item in configured_expenses[:4]
        ]
        entries = [entry for entry in entries if entry[1] > 0]
        pitch = (expense_bottom - expense_start) / max(len(entries), 1)
        expense_items = [
            (name, value, pct, pp, expense_start + index * pitch)
            for index, (name, value, pct, pp) in enumerate(entries)
        ]
        show_expense_pp = pitch >= 125.0
    else:
        expense_items = [
            (
                "R&D",
                rd_value,
                opex.get("rd_pct_rev"),
                opex.get("rd_yoy_pp"),
                expense_start + 25.0,
            ),
            (
                "SG&A",
                sga_value,
                opex.get("sga_pct_rev"),
                opex.get("sga_yoy_pp"),
                min(expense_start + 180.0, expense_bottom - 115.0),
            ),
        ]
    rendered_expenses = [item for item in expense_items if item[1] > 0]
    expense_source_spans = _bounded_stacked_spans(
        opex_top,
        opex_bottom,
        [height(item[1]) for item in rendered_expenses],
    )
    for (name, value, pct, pp, top), source_span in zip(
        rendered_expenses, expense_source_spans
    ):
        item_height = height(value, 12)
        _ribbon(
            ax,
            x_operating + operating_width,
            source_span[0],
            source_span[1],
            x_final,
            top,
            top + item_height,
            RED_FLOW,
        )
        _bar(ax, x_final, top, final_width, item_height, RED_BAR)
        wrapped_name = textwrap.fill(name, width=18)
        name_lines = wrapped_name.count("\n") + 1
        ax.text(
            1764,
            top + 8,
            wrapped_name,
            ha="left",
            va="top",
            linespacing=0.92,
            color=RED,
            **_font(16, "bold"),
        )
        amount_y = top + 48 + (name_lines - 1) * 24
        ax.text(
            1764,
            amount_y,
            _money(value, unit, True),
            ha="left",
            color=RED,
            **_font(15),
        )
        if pct is not None:
            ax.text(
                1764,
                amount_y + 33,
                _percent(pct, " of revenue"),
                ha="left",
                color=MUTED,
                **_font(14),
            )
        if pp is not None and show_expense_pp:
            ax.text(
                1764,
                amount_y + 63,
                _pp(pp),
                ha="left",
                color=MUTED,
                **_font(13),
            )

    source_label = _source_label(data)
    ax.text(1000, 1066, source_label, ha="center", color=SOURCE, **_font(13, "bold"))
    ax.text(
        1000,
        1094,
        "For information only, not investment advice",
        ha="center",
        color=MUTED,
        **_font(10),
    )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, facecolor=BG)
    plt.close(fig)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_json", type=Path)
    parser.add_argument("-o", "--out", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=100)
    args = parser.parse_args()
    data = json.loads(args.data_json.read_text())
    print(render(data, args.out, dpi=args.dpi))


if __name__ == "__main__":
    main()
