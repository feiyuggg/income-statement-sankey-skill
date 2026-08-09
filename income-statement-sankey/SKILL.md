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
6. Prefer the local Python runtime when it already has `matplotlib` and
   `Pillow`; this avoids repeated `uv` dependency resolution and network
   retries. Check once per session:

```bash
python3 -c 'import matplotlib, PIL'
```

7. Validate and render through the fast path. It combines strict validation,
   rendering, parallel workers, and a content-hash cache:

```bash
python3 <SKILL_DIR>/scripts/build_batch.py DATA.json \
  --out-dir OUTPUT_DIR
```

If the import check fails, replace `python3` with `uv run` in that command.
The legacy separate validator remains available when diagnosing bad data:

```bash
python3 <SKILL_DIR>/scripts/validate_data.py DATA.json
```

8. For a single custom output filename, the compatible one-shot command is:

```bash
python3 <SKILL_DIR>/scripts/build_chart.py \
  --from-json DATA.json \
  --validate \
  -o OUTPUT.png
```

9. Inspect the PNG before delivery. Compare the composition with
   `assets/reference-layout.jpg` and the renderer result with
   `assets/reference-output.png`; fix clipping, overlap, wrong ordering, or
   unreadable labels.
10. Return the PNG plus a concise analysis of revenue mix, growth, margins, and
   unusual movements. Cite the official sources used.

`<SKILL_DIR>` is the directory containing this `SKILL.md`.

## Fast path for multiple periods

When the user requests multiple quarters or companies, avoid repeating the
single-chart workflow from scratch:

1. Resolve the full official report list once before extraction. Download or
   open each official document once and keep a shared manifest containing the
   period, publication date, official URL, and local cached path.
2. Extract independent periods in parallel, with one bounded worker per period
   and at most six workers. Give every worker the shared manifest and one output
   JSON path; do not let workers rediscover the report list.
3. Reuse a period ledger for overlapping comparisons. If Q2 2025 is already an
   extracted current period, reuse its values as the prior period for Q2 2026
   instead of opening and extracting the same disclosure again.
4. Run one batch command after all JSON files exist:

```bash
python3 <SKILL_DIR>/scripts/build_batch.py DATA_DIR/*.json \
  --out-dir OUTPUT_DIR --jobs 5
```

5. Keep the `.sankey-cache.json` sidecars. Unchanged JSON plus unchanged
   renderer code is reported as `CACHED` and is not rendered again. Use
   `--force` only after an external asset changed without a JSON or renderer
   change.
6. Do a two-level visual check: scan all outputs together at reduced size, then
   inspect only suspicious charts at full resolution. Every final PNG still
   requires a visual verdict; the contact scan only avoids repeatedly opening
   obviously clean charts at full size.

Do not parallelize dependent work: period discovery must finish before
quarter-specific extraction, and every JSON must validate before deployment.

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
- Treat bars, complete text bounding boxes, ribbons, the footer, and the canvas
  edge as shared layout obstacles. Enforce explicit vertical clearance for
  bar-to-bar, label-to-label, label-to-bar, and label-to-ribbon pairs instead
  of resolving each element with isolated fixed offsets.
- Generate multiple label anchors when space is constrained. Labels may sit
  above, below, left, right, or inside a sufficiently large bar; choose the
  nearest in-bounds candidate whose complete text bounding box clears other
  labels, bars, and important ribbons. A label is not required to stay above
  its bar.
- Preserve the same vertical ordering at both ends of sibling ribbons. Assign
  source intervals by destination Y order so Net, Tax, negative Other, and
  future right-column flows remain monotonic and do not cross because of an
  index-order mismatch.
- Compute the right-side profit layout from rendered heights instead of fixed
  Y coordinates. Net profit/loss, Tax, and expense-detail sinks must be stacked
  with explicit vertical gaps, including enough clearance for the four-line net
  label block when the net bar is short.
- When positive non-operating income is unusually large, place its source bar
  below the operating-expense bar and keep its bottom above the footer when
  possible. In high-margin layouts with a short positive Other bar, place it
  above the operating-expense label and bar so its Tax/Net ribbons do not cross
  operating-expense detail ribbons. Do not put horizontal text inside a narrow
  source bar; move the label into adjacent whitespace instead.
- Put the Operating expenses label in the open gap between operating profit and
  the expense bar only when that gap can contain the complete three-line text
  bounding box plus explicit clearance; otherwise place it below the expense
  bar in the left-side label lane and move later source bars below the label
  block. Do not center fallback text over outgoing profit ribbons.
- Place short positive Other labels in the left-side label lane rather than
  below their source bar. Stack negative Other sinks below Tax (or below the
  complete net-profit label block when Tax is absent), and reserve space before
  expense-detail sinks begin.
- Apply the same rendered-height rule to Cost of revenue: center its complete
  three-line label block between gross profit and the cost bar only when the
  gap is safe, otherwise place the label below the cost bar. Do not use fixed Y
  coordinates for either expense label.
- Left-align long expense-detail labels to the right of their sink bars and
  distribute both custom items and the default R&D/SG&A breakdown across the
  remaining right-column height. As per-item pitch tightens, hide YoY copy,
  then revenue-share copy, and finally combine the name and amount in dense
  four-item layouts instead of allowing adjacent labels to overlap.
- Keep every detail ribbon's source interval inside its parent bar. Minimum
  visible heights may enlarge destination bars, but must not be reused for
  source-flow accounting or cumulative source cursors.
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
python3 <SKILL_DIR>/scripts/build_batch.py \
  <SKILL_DIR>/scripts/examples/aapl_q3_fy26_full.json \
  --out-dir /tmp/income-sankey-render
```

## Delivery checklist

- Official period, publication date, and source URLs opened and verified.
- Segment amounts and shares shown.
- Revenue, gross profit, operating profit, and net profit reconciled.
- Same-quarter YoY comparisons used.
- PNG inspected at full resolution.
- Official sources cited.
- Output clearly marked informational, not investment advice.
