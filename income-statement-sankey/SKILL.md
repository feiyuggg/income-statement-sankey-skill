---
name: income-statement-sankey
description: 拉取并核验上市公司季度或年度财报，分析收入组成、收入占比、同比变化、毛利、营业利润、净利润及费用结构，并生成与用户参考图同版式的 2000x1122 收入利润桑基图 PNG。用于“给我一份财报收入图”“收入组成图”“财报桑基图”“利润表拆解图”“earnings chart”“income statement sankey”以及要求按参考图一比一复刻财报信息图的请求。
---

# Income Statement Sankey

Produce a source-recorded, reconciled income-statement Sankey PNG whose geometry
follows the bundled original reference in `assets/reference-layout.jpg`.
Use `assets/reference-output.png` as the deterministic renderer regression
baseline.

## Required workflow

1. Resolve the company, ticker, reporting period, fiscal-quarter label, currency,
   and unit. Interpret "latest" as the latest report published as of the current
   date, not the latest period present in an aggregator.
2. Retrieve the official earnings release, shareholder letter, 10-Q/10-K, 20-F,
   or equivalent filing. Prefer company IR and regulator filings.
3. Use `scripts/fetch_income.py` only as a secondary core-P&L fetch and
   cross-check. Never use Yahoo-derived product segments as authoritative.
4. Open the official documents and extract current and same-period-prior-year
   values. Record publisher, retrieval date, source labels, and URLs in
   `source_records`.
5. Build one complete JSON file following `references/data-schema.md`.
6. Run strict validation:

```bash
uv run <SKILL_DIR>/scripts/validate_data.py DATA.json
```

7. Render only after validation passes:

```bash
uv run <SKILL_DIR>/scripts/build_chart.py \
  --from-json DATA.json \
  --validate \
  -o OUTPUT.png
```

8. Inspect the PNG before delivery. Compare the composition with
   `assets/reference-layout.jpg` and the renderer result with
   `assets/reference-output.png`; fix clipping, overlap, wrong ordering, or
   unreadable labels.
9. Return the PNG plus a concise analysis of revenue mix, growth, margins, and
   unusual movements. Cite the official sources used.

`<SKILL_DIR>` is the directory containing this `SKILL.md`.

## Data rules

- Do not invent segments, totals, YoY, margin changes, logos, or fiscal labels.
- Calculate and display revenue shares from unrounded source values.
- Reconcile all required identities within the tight tolerance accepted by
  `validate_data.py`; do not validate rounded display-only inputs.
- Supply `prior_period` so the validator can recompute YoY and margin changes.
- Keep reported company taxonomy. Do not force every company into
  Products/Services. Use `revenue_groups` for arbitrary business groups.
- For conglomerates, insurers, banks, and holding companies, use the reported
  **business segment** footnote rather than income-statement line items, and set
  `layout.style: "conglomerate"`. That layout has no gross-profit line, so none
  has to be invented; segment profits must reconcile to operating profit. See
  `references/data-schema.md`.
- Require at least two company-reported revenue groups. Product/category
  segments may be omitted only when the official filing does not disclose them.
- Treat negative other income as an expense and color it red.
- Preserve the sign of net income. Render a negative amount as a red `Net loss`
  node, with operating profit visibly offsetting the non-operating expense flow.
- Put estimates in `estimates` and label them in the footer. Do not silently
  mix estimates with reported figures.
- Use the filing's presentation currency. Convert only when the user asks.

## Visual rules

- Output exactly `2000x1122` pixels unless the user explicitly requests another
  size.
- Preserve the reference flow: segments -> revenue group -> total revenue ->
  gross profit/cost of revenue -> operating profit/operating expenses -> net
  profit/tax/other/R&D/SG&A.
- Use black revenue bars, gray revenue ribbons, green profit ribbons, and red
  cost ribbons on a light-gray background.
- Use direct labels, not floating cards.
- Keep labels outside ribbons and maintain proportional bar/ribbon thickness.
- Add a company logo only from an official or user-supplied asset. Text is the
  fallback.
- Do not reproduce another publisher's logo or imply their authorship. Replace
  the publisher footer with real data-source labels.
- Use `references/layout-spec.md` for coordinates, typography, and optional
  asset fields.

## Useful commands

Fetch a secondary P&L draft:

```bash
uv run <SKILL_DIR>/scripts/fetch_income.py AAPL --quarter 0 \
  --out /tmp/aapl-core.json
```

Merge an official segment overlay and render:

```bash
uv run <SKILL_DIR>/scripts/build_chart.py AAPL \
  --segments /tmp/aapl-official-segments.json \
  --save-json /tmp/aapl-complete.json \
  --validate \
  -o /tmp/aapl-income-sankey.png
```

Render the deterministic example:

```bash
uv run <SKILL_DIR>/scripts/build_chart.py \
  --from-json <SKILL_DIR>/scripts/examples/aapl_q3_fy26_full.json \
  --validate \
  -o /tmp/aapl-reference-test.png
```

## Delivery checklist

- Official period, publication date, and source URLs opened and verified.
- Segment amounts and shares shown.
- Revenue, gross profit, operating profit, and net profit reconciled.
- Same-quarter YoY comparisons used.
- PNG inspected at full resolution.
- Official sources cited.
- Output clearly marked informational, not investment advice.
