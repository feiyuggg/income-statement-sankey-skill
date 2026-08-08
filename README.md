# Income Statement Sankey Skill

A Codex skill that retrieves official earnings data, analyzes revenue mix and
profit structure, validates the numbers, and renders a deterministic
`2000x1122` income-statement Sankey PNG.

The chart includes:

- Company-reported revenue groups and their revenue shares
- Optional product/category segments
- Revenue, gross profit, cost of revenue, operating expenses, operating income,
  tax, other income, and net income
- Recomputed year-over-year growth and margin changes
- Source labels from company investor relations or regulatory filings

## Install

Clone the repository and link the skill into your Codex skills directory:

```bash
git clone https://github.com/feiyuggg/income-statement-sankey-skill.git
mkdir -p ~/.codex/skills
ln -s "$PWD/income-statement-sankey-skill/income-statement-sankey" \
  ~/.codex/skills/income-statement-sankey
```

Restart Codex after installation.

## Use

Typical prompts:

```text
给我一份苹果最新季度财报收入图
分析微软收入组成和占比，生成财报桑基图
Create an income statement Sankey for the latest reported quarter of GOOGL
```

The skill directs Codex to:

1. Resolve the exact reporting period and publication date.
2. Open official investor-relations or regulatory documents.
3. Extract current and same-period-prior-year values.
4. Recompute revenue shares, YoY growth, and margin changes.
5. Reconcile the income statement under a tight tolerance.
6. Render and visually inspect the PNG before delivery.

## Validate And Render

```bash
uv run income-statement-sankey/scripts/validate_data.py DATA.json

uv run income-statement-sankey/scripts/build_chart.py \
  --from-json DATA.json \
  --validate \
  -o OUTPUT.png
```

Render the bundled verified example:

```bash
uv run income-statement-sankey/scripts/build_chart.py \
  --from-json income-statement-sankey/scripts/examples/aapl_q3_fy26_full.json \
  --validate \
  -o /tmp/aapl-income-statement.png
```

## Data Integrity

Yahoo Finance support is included only as a secondary core-P&L cross-check.
Strict validation requires an official or regulatory source record, complete
revenue composition, core income-statement identities, and prior-period values
that independently reproduce the displayed YoY metrics.

URL metadata checks reduce obvious source spoofing but cannot prove document
contents. The agent must open and inspect each official source before using it.

## Assets And Trademarks

The repository includes the complete visual material bundle used to reproduce
the example:

- `assets/reference-layout.jpg`: the original layout reference
- `assets/reference-output.png`: the renderer's verified output
- `assets/apple-touch-icon.png`: an optional Apple brand asset

The original layout reference, company logo, company names, and trademarks are
third-party material and are not licensed under this repository's MIT License.
See `THIRD_PARTY_NOTICES.md` before redistributing or publishing derived work.
For other companies, add a logo only when it is user-supplied or obtained from
an official source with appropriate permission; otherwise the renderer uses
text.
