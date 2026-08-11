# Income Statement Sankey - Data Schema

Intermediate JSON consumed by `render_sankey.py`.

```json
{
  "company": "Apple",
  "ticker": "AAPL",
  "period_label": "Q3 FY26",
  "period_end_label": "Ending June 2026",
  "currency": "USD",
  "unit": "B",
  "brand": {
    "logo_text": "AAPL"
  },
  "source_records": [
    {
      "label": "Apple FY26 Q3 financial statements",
      "type": "official_ir",
      "publisher": "Apple Inc.",
      "retrieved_on": "2026-08-08",
      "url": "https://www.apple.com/newsroom/pdfs/fy2026q3/FY26_Q3_Consolidated_Financial_Statements.pdf"
    }
  ],

  "segments": [
    {
      "name": "iPhone",
      "revenue": 54.3,
      "yoy_pct": 22.0,
      "group": "products",
      "subtitle": null,
      "icon_path": null
    },
    {
      "name": "Mac",
      "revenue": 10.4,
      "yoy_pct": 29.0,
      "group": "products",
      "subtitle": "Air, Pro, Mini"
    },
    {
      "name": "iPad",
      "revenue": 6.2,
      "yoy_pct": -6.0,
      "group": "products",
      "subtitle": null
    },
    {
      "name": "Watch / AirPods",
      "revenue": 7.9,
      "yoy_pct": 6.0,
      "group": "products",
      "subtitle": "Wearables, Home, and Accessories"
    }
  ],

  "revenue_groups": [
    { "id": "products", "name": "Products", "revenue": 78.7, "yoy_pct": 18.0 },
    { "id": "services", "name": "Services", "revenue": 30.7, "yoy_pct": 12.0 }
  ],
  "products": { "revenue": 78.7, "yoy_pct": 18.0 },
  "services": { "revenue": 30.7, "yoy_pct": 12.0 },
  "total_revenue": { "revenue": 109.4, "yoy_pct": 16.0 },

  "gross_profit": { "amount": 54.8, "margin_pct": 50.0, "margin_yoy_pp": 4.0 },
  "cogs": {
    "amount": 54.6,
    "products": 47.1,
    "products_gm_pct": 40.0,
    "services": 7.5,
    "services_gm_pct": 76.0
  },

  "operating_profit": { "amount": 35.7, "margin_pct": 33.0, "margin_yoy_pp": 3.0 },
  "opex": {
    "amount": 19.1,
    "rd": 11.7,
    "rd_pct_rev": 11.0,
    "rd_yoy_pp": 1.0,
    "sga": 7.3,
    "sga_pct_rev": 7.0,
    "sga_yoy_pp": 0.0
  },

  "net_profit": { "amount": 29.8, "margin_pct": 27.0, "margin_yoy_pp": 2.0 },
  "tax": 6.4,
  "other_income": 0.6,
  "prior_period": {
    "total_revenue": 94.0,
    "revenue_groups": [
      { "id": "products", "revenue": 66.6 },
      { "id": "services", "revenue": 27.4 }
    ],
    "segments": [
      { "name": "iPhone", "revenue": 44.6 }
    ],
    "gross_profit": 43.7,
    "operating_profit": 28.2,
    "net_profit": 23.4,
    "opex": { "rd": 8.9, "sga": 6.7 }
  },
  "estimates": []
}
```

## Field rules

| Field | Meaning |
|-------|---------|
| amounts | In `unit` (default billions). Cost lines are positive magnitudes; `net_profit.amount` retains its reported sign. |
| `yoy_pct` | Year-over-year % change of the dollar amount |
| `margin_pct` | Amount / total_revenue × 100 |
| `*_yoy_pp` | Year-over-year change in margin/ratio, in percentage **points** |
| `tax` | Tax provision. Positive values draw as an expense outflow; when net income is positive, negative values draw as a green tax-benefit inflow to net profit. |
| `other_income` | Non-operating other (can be negative) |
| `net_profit.amount` | Net income is positive; net loss is negative and renders as a red loss node. |
| `source_records` | Auditable sources with publisher, retrieval date, and HTTPS URL. At least one official or regulatory record is required. The agent must still open and inspect the document; metadata validation cannot prove its contents. |
| `revenue_groups` | At least two company-reported revenue components. Shares are calculated by the renderer. |
| `segments` | Optional. If empty, left side shows only Products + Services bars |
| `prior_period` | Required same-period-prior-year values used to recompute YoY and margin changes. |
| `brand.logo_path` | Optional official or user-supplied image. Relative paths resolve from the skill directory. |
| `brand.logo_color` | Optional monochrome tint, useful for official marks supplied on a white background. |
| `brand.logo_text` | Fallback text when no valid logo image is available. |
| `segments[].icon_path` | Optional official or user-supplied segment icon. |
| `cogs.products` / `cogs.services` | Optional. If missing, only total COGS is shown |
| `estimates` | Optional explicit estimate disclosures; never mix estimates silently with reported values. |

## Identity checks

```
sum(revenue_groups.revenue) ~= total_revenue.revenue
sum(segments grouped by group) ~= matching revenue_group.revenue
gross_profit + cogs ~= total_revenue
operating_profit + opex ~= gross_profit
net_profit + tax ~= operating_profit + other_income
```

`validate_data.py` uses the larger of 0.01 units or 0.01% of revenue unless
`--tolerance` is supplied. Use unrounded reported values so strict validation
does not hide material differences.

## Conglomerate / financial style (`layout.style: "conglomerate"`)

Insurers, banks, and holding companies report **business segments**, not a
product/service split, and have no meaningful gross profit or R&D line. The
default schema hard-requires `gross_profit`, `cogs`, `opex.rd`, and `opex.sga`,
so it cannot describe them without inventing figures. Setting `layout.style`
to `"conglomerate"` selects a second layout and a matching validation branch:

```
segments (+ revenue_other) -> Revenue
Revenue -> operating_profit + operating_costs
operating_profit + investment_gains + other_income -> pretax_profit
pretax_profit -> net_profit + tax
```

No gross-profit column, no COGS column, no opex breakdown column.

```json
{
  "layout": { "style": "conglomerate" },
  "footer_note": "Segment margin = segment EBT / segment revenues",
  "segments": [
    { "name": "Insurance", "revenue": 26.176, "profit": 5.865,
      "yoy_pct": -0.3, "margin_pct": 22.4 },
    { "name": "BNSF", "revenue": 6.601, "profit": 2.061,
      "yoy_pct": 14.4, "margin_pct": 31.2 }
  ],
  "revenue_other": { "name": "Other", "amount": 0.794 },
  "total_revenue": { "revenue": 101.808, "yoy_pct": 10.0 },
  "operating_profit": { "amount": 14.376, "margin_pct": 14.1, "margin_yoy_pp": -0.3 },
  "operating_costs": { "amount": 87.432 },
  "investment_gains": { "amount": 16.077 },
  "other_income": 1.610,
  "pretax_profit": { "amount": 32.063, "label": "Net profit before tax" },
  "net_profit": { "amount": 25.772, "margin_pct": 25.3, "margin_yoy_pp": 11.8 },
  "tax": 6.291,
  "prior_period": {
    "total_revenue": 92.515,
    "operating_profit": 13.378,
    "net_profit": 12.457,
    "segments": [{ "name": "Insurance", "revenue": 26.248, "profit": 6.537 }]
  }
}
```

| Field | Meaning |
|-------|---------|
| `segments[].profit` | **Required.** Segment earnings before income taxes. Segment profits must sum to `operating_profit`, which is what makes the segment table auditable. |
| `segments[].margin_pct` | **Required.** Verified against `profit / revenue`. |
| `revenue_other` | Reconciling revenue (corporate, eliminations) drawn as a green inflow merging into the revenue bar. |
| `operating_costs` | Total costs and expenses of the operating businesses. Replaces `cogs` + `opex`. |
| `investment_gains` | Non-operating investment gains/losses; drawn as an inflow to the pre-tax node. May be negative. |
| `pretax_profit.label` | Optional node label, e.g. `"Net profit before tax"`. |
| `footer_note` | Optional extra footer clause appended after the source labels. |
| `prior_period.segments[]` | Prior-year segment revenue keyed by `name`, used to recompute each segment's Y/Y. |

### Identity checks (conglomerate)

```
sum(segments.revenue) + revenue_other.amount ~= total_revenue.revenue
sum(segments.profit)                         ~= operating_profit
operating_profit + operating_costs           ~= total_revenue.revenue
operating_profit + investment_gains + other_income ~= pretax_profit
net_profit + tax                             ~= pretax_profit
```

Every Y/Y and `margin_yoy_pp` is recomputed from `prior_period`, exactly as in
the default branch. Because `net_profit + tax` must equal pre-tax profit
exactly, use **total net earnings** here and state the amount attributable to
shareholders in the write-up. Up to 9 segments are supported.

Working example: `scripts/examples/brk_q2_2026_conglomerate.json`.
