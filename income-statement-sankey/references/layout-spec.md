# Layout Spec - Reference-Matched Income Statement Sankey

Match the geometry in the self-generated `assets/reference-output.png`.

## Canvas

- Exact default output: **2000x1122**
- Background: `#F4F4F4`
- Title: bold dark teal `#15577A`, centered top
- Top-right: period badge (`Q3 FY26` / `Ending June 2026`)
- Footer: real data-source labels plus an informational disclaimer

## Color system

| Role | Fill | Text |
|------|------|------|
| Revenue / neutral flows | `#929292` -> bars `#050505` | dark |
| Gross / operating / net **profit** | bar `#27AA27`, ribbon `#A4CFA0` | green |
| Costs / opex / tax | bar `#E00000`, ribbon `#E9958D` | red |
| Other income (small) | green-ish muted | green |

## Column order (left → right)

1. **Segment bars** (optional product lines)
2. **Products** + **Services** stacks
3. **Total Revenue** (black center bar under company logo/name)
4. Split to **Gross profit** (green) + **Cost of revenue** (red)
5. COGS splits to **Products COGS** / **Services COGS** (if available)
6. Gross profit splits to **Operating profit** + **Operating expenses**
7. OpEx splits to **R&D** + **SG&A**
8. Operating profit → **Net profit** + **Tax** (+ **Other** if material)

## Label patterns (must match style)

- Revenue group: `$78.7B` + `72% of revenue` + `+18% Y/Y`
- Revenue: `$54.3B` + `+22% Y/Y` (negative YoY in parentheses, e.g. `(6%) Y/Y`)
- Profit: `$54.8B` + `50% margin` + `+4pp Y/Y`
- Cost: `($54.6B)` for expense lines on the right edge
- OpEx share: `11% of revenue` + `+1pp Y/Y`

## Visual rules

- Bar heights proportional to dollar amount within each column
- Flow ribbons (sankey polygons) connect columns; opacity ~0.55–0.75
- Allocate stacked source-flow intervals from actual values and keep them
  bounded by the parent bar. A minimum visible destination-bar height must not
  enlarge or move the corresponding source interval.
- Do **not** invent segment numbers - leave segments empty when unknown
- Prefer exact reported figures over estimates; note estimates in footer if any
- Direct labels only; do not place the chart inside cards
- Relative `brand.logo_path` and `segments[].icon_path` values resolve from the
  skill directory
- `brand.logo_color` can convert an official light-background logo into a
  monochrome mark while preserving its silhouette
- Keep all text within the 2000x1122 canvas and visually inspect every output

## Conglomerate style column order

Selected by `layout.style: "conglomerate"` (see `data-schema.md`). Same canvas,
palette, and typography; different columns:

1. **Segment bars** (up to 9), each labelled with amount, Y/Y, and its own margin
2. Optional **Other** revenue inflow (green) merging into the revenue bar
3. **Total Revenue** (black bar under the company logo/name)
4. Split to **Operating profit** (green) + **Operating costs and expenses** (red)
5. **Investment gains** and **Other** as green inflow bars below operating profit
6. All three merge into the **pre-tax** node
7. Pre-tax splits to **Net profit** + **Tax**

Segment slots are sized from each label's real line count, so long segment names
never collide; the left band is `236..1040`, with the revenue-side Other node
reserved out of it.

## Company-specific segments

| Ticker | Typical product segments | Services |
|--------|--------------------------|----------|
| AAPL | iPhone, Mac, iPad, Wearables | Services |
| MSFT | (often Productivity, Intelligent Cloud, More Personal Computing) | mixed |
| GOOGL | Search, YouTube, Network, Cloud, Other | etc. |
| META | Family of Apps, Reality Labs | — |
| AMZN | Online stores, 3P, AWS, Ads, Subscription… | — |

Agent should pull segment tables from latest earnings release / 10-Q when yfinance lacks them.
