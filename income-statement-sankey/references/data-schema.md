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
| amounts | In `unit` (default billions). Positive numbers. |
| `yoy_pct` | Year-over-year % change of the dollar amount |
| `margin_pct` | Amount / total_revenue × 100 |
| `*_yoy_pp` | Year-over-year change in margin/ratio, in percentage **points** |
| `tax` | Tax provision (drawn as outflow / expense) |
| `other_income` | Non-operating other (can be negative) |
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
