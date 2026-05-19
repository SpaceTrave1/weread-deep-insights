---
name: weread-deep-insights
description: Generate evidence-based deep reading profile reports from WeRead/微信读书 personal data. Use when the user asks to export or analyze full WeRead reading records, shelf, reading progress, notebooks, highlights, personal reviews, reading themes, thinking style, values, anxieties, long-term interests, growth advice, or HTML/Markdown reading reports.
---

# WeRead Deep Insights

Create a deep reading profile from full WeRead personal records and notes. The skill exports all relevant personal reading data available through the WeRead Agent Gateway, analyzes actual note content rather than only counting keywords, and writes reports in HTML and Markdown.

## Quick Start

Run the report generator from the skill folder or pass the skill path explicitly:

```bash
python scripts/generate_deep_report.py --format both --output-dir ./weread-reports
```

Requirements:

- `WEREAD_API_KEY` must be set in the environment or in a local `.env` file.
- Network access is required to call `https://i.weread.qq.com/api/agent/gateway`.
- No third-party Python package is required.

## Outputs

- `weread_deep_report.md`: readable report for editing, archiving, or sharing as text.
- `weread_deep_report.html`: self-contained offline HTML report.

The report should emphasize:

- Reading overview and official export coverage, compressed into a short evidence section.
- Top reading categories, books, authors, years, shelf composition, and notes.
- Themes, recurring questions, people/authors, thinking style, values, anxieties, and long-term directions.
- Evidence snippets from the user's own personal reviews/notes when available.
- A concise reader-archetype label for the opening hero and a visualized HTML report with colorful SVG section icons, layered metric cards, section overview panels, bars, bubbles, value-signal cards, and pie/donut charts.
- Information-cocoon risk assessment and personalized antidotes based on theme/category concentration.
- Personalized recommendation book list that skips books already visible in the user's records when possible.
- Concise reading, writing, thinking, and personal growth suggestions.
- A stricter personal diagnosis section with blind spots, dimension scores, and concrete execution advice.

## Workflow

1. If the user asks for a report, run `scripts/generate_deep_report.py`.
2. If they only want raw collection behavior or endpoint coverage, read `references/api-coverage.md`.
3. If they ask to adjust interpretation style, read `references/analysis-rubric.md`.
4. Prefer `--format both` unless the user asks for only HTML or only Markdown.
5. For large accounts, start with a full run. Use `--max-note-books N` only for quick tests.

## Important Rules

- Do not mix public book reviews or recommendation data into the user's personal profile unless explicitly requested.
- Treat `/user/notebooks` `noteCount` as underline count, not total notes. Total note count is `reviewCount + noteCount + bookmarkCount`.
- Fetch notebook pages with `lastSort`; do not use offset/limit.
- For content analysis, combine `/book/bookmarklist` and `/review/list/mine`; prefer personal reviews for quoted evidence.
- Reading time fields from `/readdata/detail` and `/book/getprogress` are seconds.
- If the evidence is thin, say "只能初步推测" rather than overclaiming.
- Avoid MBTI-style definitive personality labels. Use reading tendencies and evidence-backed behavioral language.
- The strict analysis section may be blunt, but it must stay evidence-based and avoid insults or psychological diagnosis.

## Script Options

```bash
python scripts/generate_deep_report.py \
  --format both \
  --output-dir ./weread-reports \
  --title "我的微信读书深度画像"
```

Useful options:

- `--format html|markdown|both`: output format.
- `--output-dir PATH`: destination folder.
- `--title TEXT`: report title.
- `--max-note-books N`: limit per-book note fetching for quick tests.
- `--skip-progress`: skip shelf progress calls for faster runs.
- `--skip-book-info`: skip detailed book metadata calls for faster runs.
- `--timeout SECONDS`: API request timeout.
