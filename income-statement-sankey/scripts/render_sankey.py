#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "matplotlib>=3.8",
#     "pillow>=10",
# ]
# ///
"""Render a 2000x1122 reference-style income-statement Sankey PNG."""

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
    text = f"${abs(float(value)):.1f}{unit}"
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
    return " | ".join(labels[:2]) or "Official company filing"


def render(data: dict[str, Any], out_path: Path, dpi: int = 100) -> Path:
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

    ax.text(
        1000,
        105,
        f"{company} {period} Income Statement",
        ha="center",
        va="center",
        color=TITLE,
        **_font(65, "bold"),
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
    has_segment_column = any(
        segment.get("revenue") is not None
        for segment in data.get("segments") or []
    )
    # Three or more groups produce bars too tall to stack a four-line label above
    # each one; the label lands on the bar above it. Place the block beside the
    # bar instead, which is only viable when no segment column sits to the left.
    groups_beside = len(groups) >= 3 and not has_segment_column
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
        if groups_beside:
            label_x = x_group - 18
            label_ha = "right"
            name_y = center - 50
            amount_y, pct_y, yoy_y = center - 7, center + 26, center + 58
        else:
            if len(groups) == 2:
                label_y = 300.0 if group_index == 0 else 760.0
            else:
                label_y = group_top - 65 if center < 650 else group_top - 54
            label_x = x_group + group_width / 2
            label_ha = "center"
            name_y = label_y
            amount_y, pct_y, yoy_y = label_y + 43, label_y + 76, label_y + 108
        ax.text(
            label_x,
            name_y,
            group["name"],
            ha=label_ha,
            va="center",
            color=DARK,
            **_font(22, "bold"),
        )
        ax.text(
            label_x,
            amount_y,
            _money(group["revenue"], unit),
            ha=label_ha,
            va="center",
            color=DARK,
            **_font(21),
        )
        ax.text(
            label_x,
            pct_y,
            _percent(group["revenue"] / revenue * 100, " of revenue"),
            ha=label_ha,
            va="center",
            color=MUTED,
            **_font(14),
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
    ][:6]
    if segments:
        if len(segments) == 1:
            centers = [485.0]
        elif len(segments) == 4:
            centers = [390.0, 580.0, 710.0, 805.0]
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
            label_x = 255
            ha = "right"
            if not icon_drawn:
                ax.text(
                    label_x,
                    center,
                    str(segment.get("name") or ""),
                    ha=ha,
                    va="center",
                    color=DARK,
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
                ha="left",
                va="center",
                color=DARK,
                **_font(19),
            )
            ax.text(
                x_segment - 20,
                amount_y + 34,
                _yoy(segment.get("yoy_pct")),
                ha="left",
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
    # Fixed slot assumes a ~33% operating margin. A very high margin grows the
    # green bar past it, which would draw the red bar inside the green one and
    # visually truncate it. Push down only when it would actually collide.
    opex_top = max(590.0, operating_bottom + 12.0)
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
    ax.text(1440, opex_top + 86, "Operating", ha="center", color=RED, **_font(19, "bold"))
    ax.text(1440, opex_top + 118, "expenses", ha="center", color=RED, **_font(19, "bold"))
    ax.text(
        1440,
        opex_top + 158,
        _money(opex_value, unit, True),
        ha="center",
        color=RED,
        **_font(18),
    )

    product_cogs = cogs.get("products")
    service_cogs = cogs.get("services")
    cogs_parts: list[tuple[str, float, Any]] = []
    if product_cogs is not None:
        cogs_parts.append(("Products", float(product_cogs), cogs.get("products_gm_pct")))
    if service_cogs is not None:
        cogs_parts.append(("Services", float(service_cogs), cogs.get("services_gm_pct")))
    if cogs_parts:
        source_cursor = cogs_top
        part_tops = [790.0, 960.0]
        for index, (name, value, margin) in enumerate(cogs_parts[:2]):
            part_height = height(value, 12)
            part_top = part_tops[index]
            part_bottom = part_top + part_height
            _ribbon(
                ax,
                x_gross + split_width,
                source_cursor,
                source_cursor + part_height,
                x_cost_detail,
                part_top,
                part_bottom,
                RED_FLOW,
            )
            source_cursor += part_height
            _bar(ax, x_cost_detail, part_top, detail_width, part_height, RED_BAR)
            text_y = 808.0 if index == 0 else 918.0
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

    ax.text(1175, 942, "Cost of", ha="center", color=RED, **_font(19, "bold"))
    ax.text(1175, 974, "revenue", ha="center", color=RED, **_font(19, "bold"))
    ax.text(1175, 1012, _money(cogs_value, unit, True), ha="center", color=RED, **_font(17))

    net_height = height(net_value)
    net_top = 310.0
    net_bottom = net_top + net_height

    # Geometry of every outflow leaving the operating bar, resolved before any
    # ribbon is drawn. The slots must clear both the net-profit bar and the
    # operating bar: sitting below operating_bottom is what makes the red flows
    # sweep downward while the green one sweeps up, so the two visually diverge
    # instead of the red bars being drawn inside the green one.
    final_cursor = max(net_bottom, operating_bottom) + 8.0
    has_other = abs(other_value) > 0.05
    other_height = height(other_value, 10) if has_other else 0.0
    other_top = max(430.0, final_cursor) if has_other else 0.0
    if has_other:
        final_cursor = other_top + other_height + 8.0
    has_tax = tax_value > 0
    tax_height = height(tax_value, 11) if has_tax else 0.0
    tax_top = max(495.0, final_cursor) if has_tax else 0.0

    # Previously every outflow anchored its source to operating_bottom, so the
    # ribbons overlapped each other (Other sat entirely inside Tax) and all
    # curved upward across the green band. Partition the bar's right edge into
    # consecutive disjoint slices instead, ordered by target position: the top
    # slice (net profit) sweeps up, the lower slices sweep down, and no two
    # ribbons share a single source pixel.
    outflows = [(net_top, net_bottom, net_value, GREEN_FLOW)]
    if has_other:
        outflows.append(
            (
                other_top,
                other_top + other_height,
                abs(other_value),
                GREEN_FLOW if other_value >= 0 else RED_FLOW,
            )
        )
    if has_tax:
        outflows.append((tax_top, tax_top + tax_height, tax_value, RED_FLOW))
    outflows.sort(key=lambda item: item[0])
    outflow_total = sum(item[2] for item in outflows) or 1.0
    source_cursor = operating_top
    for target_top, target_bottom, value, color in outflows:
        slice_height = operating_height * value / outflow_total
        _ribbon(
            ax,
            x_operating + operating_width,
            source_cursor,
            source_cursor + slice_height,
            x_final,
            target_top,
            target_bottom,
            color,
        )
        source_cursor += slice_height

    _bar(ax, x_final, net_top, final_width, net_height, GREEN_BAR)
    ax.text(1764, 335, "Net profit", ha="left", color=GREEN, **_font(22, "bold"))
    ax.text(1764, 375, _money(net_value, unit), ha="left", color=GREEN, **_font(20))
    ax.text(
        1764,
        412,
        _percent(net.get("margin_pct"), " margin"),
        ha="left",
        color=MUTED,
        **_font(15),
    )
    ax.text(1764, 444, _pp(net.get("margin_yoy_pp")), ha="left", color=MUTED, **_font(14))

    if has_other:
        bar_color = GREEN_BAR if other_value >= 0 else RED_BAR
        text_color = GREEN if other_value >= 0 else RED
        _bar(ax, x_final, other_top, final_width, other_height, bar_color)
        ax.text(
            1640,
            other_top + 20,
            "Other",
            ha="center",
            color=text_color,
            **_font(17, "bold"),
        )
        ax.text(
            1640,
            other_top + 52,
            _money(other_value, unit, expense=other_value < 0),
            ha="center",
            color=text_color,
            **_font(15),
        )

    if has_tax:
        _bar(ax, x_final, tax_top, final_width, tax_height, RED_BAR)
        ax.text(1816, tax_top + 17, "Tax", ha="center", color=RED, **_font(17, "bold"))
        ax.text(
            1816,
            tax_top + 51,
            _money(tax_value, unit, True),
            ha="center",
            color=RED,
            **_font(15),
        )

    expense_items = [
        (
            "R&D",
            rd_value,
            opex.get("rd_pct_rev"),
            opex.get("rd_yoy_pp"),
            640.0,
        ),
        (
            "SG&A",
            sga_value,
            opex.get("sga_pct_rev"),
            opex.get("sga_yoy_pp"),
            795.0,
        ),
    ]
    # Keep the opex detail bars below the tax slot so their ribbons also descend,
    # clearing the tax label block (not just its bar), and leave room for each
    # label block (name + amount + two ratio lines).
    expense_floor = (
        max(tax_top + tax_height + 8.0, tax_top + 81.0)
        if has_tax
        else max(net_bottom, operating_bottom) + 8.0
    )
    expense_cursor = opex_top
    for name, value, pct, pp, top in expense_items:
        if value <= 0:
            continue
        item_height = height(value, 12)
        top = max(top, expense_floor)
        expense_floor = top + max(item_height + 8.0, 125.0)
        _ribbon(
            ax,
            x_operating + operating_width,
            expense_cursor,
            min(expense_cursor + item_height, opex_bottom),
            x_final,
            top,
            top + item_height,
            RED_FLOW,
        )
        expense_cursor += item_height
        _bar(ax, x_final, top, final_width, item_height, RED_BAR)
        ax.text(1815, top + 8, name, ha="center", color=RED, **_font(17, "bold"))
        ax.text(
            1815,
            top + 42,
            _money(value, unit, True),
            ha="center",
            color=RED,
            **_font(15),
        )
        if pct is not None:
            ax.text(
                1815,
                top + 75,
                _percent(pct, " of revenue"),
                ha="center",
                color=MUTED,
                **_font(14),
            )
        if pp is not None:
            ax.text(1815, top + 105, _pp(pp), ha="center", color=MUTED, **_font(13))

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
