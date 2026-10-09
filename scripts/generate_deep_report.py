#!/usr/bin/env python3
"""Generate deep WeRead reading profile reports.

Outputs HTML and/or Markdown from successfully fetched visible records and notes.
The implementation uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, List, Optional

if __package__:
    from .evidence_bundle import prepare_bundle, validate_bundle, read_json, write_json
    from .llm_analysis import attach_insights
    from .llm_validation import validate_result
    from .analyze_bundle import add_model_args, client_from_args, run_analysis
else:
    from evidence_bundle import prepare_bundle, validate_bundle, read_json, write_json
    from llm_analysis import attach_insights
    from llm_validation import validate_result
    from analyze_bundle import add_model_args, client_from_args, run_analysis

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
    parser.add_argument("--export-analysis-bundle", type=Path, help="Save a local, masked evidence bundle for host/API analysis.")
    parser.add_argument("--analysis-input", type=Path, help="Reuse a prepared bundle without WeRead calls or .env loading.")
    parser.add_argument("--analysis-result", type=Path, help="Validate and render host/API insight JSON with --analysis-input.")
    parser.add_argument("--analysis-mode", choices=["rules", "llm"], default="rules")
    parser.add_argument("--llm-max-notes", type=int, help="Stratified whole-note selection before fragmentation.")
    parser.add_argument("--llm-fragment-chars", type=int, default=2000)
    add_model_args(parser)
    args = parser.parse_args(argv)
    if args.analysis_result and not args.analysis_input:
        parser.error("--analysis-result requires the original --analysis-input bundle")
    if args.analysis_result and args.analysis_mode == "llm":
        parser.error("Choose result import or API analysis, not both")
    if args.analysis_mode == "llm" and (not args.allow_model_upload or not args.llm_model):
        parser.error("API analysis requires --allow-model-upload and --llm-model")
    if args.llm_max_notes is not None and args.llm_max_notes < 0:
        parser.error("--llm-max-notes must be nonnegative")
    if args.llm_fragment_chars < 100:
        parser.error("--llm-fragment-chars must be at least 100")
    return args


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = None
    if args.analysis_input:
        try:
            bundle = validate_bundle(read_json(args.analysis_input))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            sys.stderr.write(f"Invalid analysis bundle ({type(exc).__name__}).\n")
            return 2
        report = bundle["baseline_report"]
        if args.title != "微信读书深度阅读画像":
            report = dict(report, title=args.title)
    else:
        data = collect_data(args)
        report = analyze(data, args.title)
        if args.export_analysis_bundle or args.analysis_mode == "llm":
            bundle = prepare_bundle(data, args.title, args.llm_max_notes, args.llm_fragment_chars)
    if args.export_analysis_bundle:
        write_json(args.export_analysis_bundle, bundle)

    exit_code = 0
    if args.analysis_result or args.analysis_mode == "llm":
        client = None
        try:
            if args.analysis_result:
                output = read_json(args.analysis_result)
                if isinstance(output, dict) and set(output) == {"result", "trace"}:
                    result, trace = output["result"], output["trace"]
                else:
                    result, trace = output, {}
                validate_result(result, bundle)
            else:
                client = client_from_args(args)
                output = run_analysis(bundle, client)
                result, trace = output["result"], output["trace"]
            report = attach_insights(bundle, result, trace=trace)
        except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
            # Preserve deterministic report; never echo arbitrary API/error text.
            report = attach_insights(bundle, failure=f"增强分析失败（{type(exc).__name__}），已回退。",
                                     trace=client.trace if client else {})
            sys.stderr.write(f"Enhanced analysis failed ({type(exc).__name__}); writing local report.\n")
            exit_code = 2
        if args.title != "微信读书深度阅读画像":
            report["title"] = args.title

    skill_dir = Path(__file__).resolve().parents[1]
    template_path = skill_dir / "assets" / "report-template.html"

    # Render before writing either format, so malformed imported data cannot
    # leave a newly written Markdown report beside an old HTML report.
    outputs = []
    try:
        if args.format in {"markdown", "both"}:
            outputs.append((out_dir / "weread_deep_report.md", render_markdown(report)))
        if args.format in {"html", "both"}:
            outputs.append((out_dir / "weread_deep_report.html", render_html(report, template_path)))
    except (ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        sys.stderr.write(f"Report rendering failed ({type(exc).__name__}); no report written.\n")
        return 2
    written: List[Path] = []
    for path, content in outputs:
        path.write_text(content, encoding="utf-8")
        written.append(path)

    for path in written:
        print(path)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
