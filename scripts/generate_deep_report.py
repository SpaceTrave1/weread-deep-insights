#!/usr/bin/env python3
"""Generate deep WeRead reading profile reports.

Outputs HTML and/or Markdown from successfully fetched visible records and notes.
The implementation uses only the Python standard library.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, List, Optional

if __package__:
    from .coverage import build_coverage, coverage_lines
else:
    from coverage import build_coverage, coverage_lines


if __package__:
    from .common import API_URL, CN_TZ, PartialFetchError, SKILL_VERSION, UpgradeRequired, as_list, clean_text, date_text, fetch_state, notebook_total, seconds_text, stat_counts, truncate, ts_for_year, valid_records
    from .collection import WeReadClient, collect_book_info, collect_book_notes, collect_data, collect_notebooks, collect_progress, collect_reviews, load_env, post_json
else:
    from common import API_URL, CN_TZ, PartialFetchError, SKILL_VERSION, UpgradeRequired, as_list, clean_text, date_text, fetch_state, notebook_total, seconds_text, stat_counts, truncate, ts_for_year, valid_records
    from collection import WeReadClient, collect_book_info, collect_book_notes, collect_data, collect_notebooks, collect_progress, collect_reviews, load_env, post_json

if __package__:
    from .analysis import THEMES, THINKING_STYLES, VALUE_SIGNALS, PEOPLE_SEEDS, score_text, content_items, pick_evidence, normalized_author, people_counter, family_for_text, build_profile_summary, build_information_cocoon, BOOK_RECOMMENDATION_POOL, title_seen, build_recommended_books, build_personalized_suggestions, build_execution_advice, analyze
else:
    from analysis import THEMES, THINKING_STYLES, VALUE_SIGNALS, PEOPLE_SEEDS, score_text, content_items, pick_evidence, normalized_author, people_counter, family_for_text, build_profile_summary, build_information_cocoon, BOOK_RECOMMENDATION_POOL, title_seen, build_recommended_books, build_personalized_suggestions, build_execution_advice, analyze

if __package__:
    from .rendering import pct_bar, score_label, CHART_COLORS, fmt_number, render_donut_chart, render_markdown, metric, render_bar, quote_html, svg_icon, section_icon, section, render_profile_visual, render_information_cocoon, render_book_cards, top_segments, render_basis_charts, render_map_charts, render_theme_overview, render_thinking_overview, render_value_visual, render_people_visual, render_html
else:
    from rendering import pct_bar, score_label, CHART_COLORS, fmt_number, render_donut_chart, render_markdown, metric, render_bar, quote_html, svg_icon, section_icon, section, render_profile_visual, render_information_cocoon, render_book_cards, top_segments, render_basis_charts, render_map_charts, render_theme_overview, render_thinking_overview, render_value_visual, render_people_visual, render_html

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deep WeRead profile reports in HTML and Markdown.")
    parser.add_argument("--format", choices=["html", "markdown", "both"], default="both")
    parser.add_argument("--output-dir", default="weread-reports")
    parser.add_argument("--title", default="微信读书深度阅读画像")
    parser.add_argument("--max-note-books", type=int, default=None, help="Limit per-book note fetching for quick tests.")
    parser.add_argument("--skip-progress", action="store_true", help="Skip /book/getprogress calls for shelf books.")
    parser.add_argument("--skip-book-info", action="store_true", help="Skip /book/info calls for shelf and notebook books.")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--retries", type=int, default=3)
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    data = collect_data(args)
    report = analyze(data, args.title)

    skill_dir = Path(__file__).resolve().parents[1]
    template_path = skill_dir / "assets" / "report-template.html"

    written: List[Path] = []
    if args.format in {"markdown", "both"}:
        md_path = out_dir / "weread_deep_report.md"
        md_path.write_text(render_markdown(report), encoding="utf-8")
        written.append(md_path)
    if args.format in {"html", "both"}:
        html_path = out_dir / "weread_deep_report.html"
        html_path.write_text(render_html(report, template_path), encoding="utf-8")
        written.append(html_path)

    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
