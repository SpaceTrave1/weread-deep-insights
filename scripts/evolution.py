#!/usr/bin/env python3
"""Offline history/host workflow. Never loads .env or invokes network services."""
import argparse
import sqlite3
import sys
from pathlib import Path

if __package__:
    from .history import HistoryStore
    from .evidence_bundle import read_json, write_json
    from .evolution_analysis import prepare_extraction, merge_extractions, prepare_comparison, merge_comparisons, validate_report
    from .evolution_workflow import record_feedback, cached_results, cache_results
    from .evolution_rendering import render_markdown, render_html
else:
    from history import HistoryStore
    from evidence_bundle import read_json, write_json
    from evolution_analysis import prepare_extraction, merge_extractions, prepare_comparison, merge_comparisons, validate_report
    from evolution_workflow import record_feedback, cached_results, cache_results
    from evolution_rendering import render_markdown, render_html


def pending_report(history):
    plan = prepare_extraction(history)
    extracted = merge_extractions(history, plan, [])
    comparison = prepare_comparison(history, extracted)
    return merge_comparisons(history, comparison, [])


def write_reports(report, current_history, output_dir, fmt='both', title='我的阅读观点演化档案'):
    output_dir = Path(output_dir).resolve()
    outputs = []
    if fmt in {'both', 'markdown'}:
        outputs.append((output_dir / 'weread_deep_report.md', render_markdown(report, current_history, title)))
    if fmt in {'both', 'html'}:
        outputs.append((output_dir / 'weread_deep_report.html', render_html(report, current_history, title)))
    # Validate/render both formats first. Atomic replacement of individual files.
    output_dir.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile
    for path, text in outputs:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output_dir, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(text)
            os.replace(temporary, path)
        finally:
            if temporary and temporary.exists(): temporary.unlink()
    return [p for p, _ in outputs]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    for command in ('ingest', 'prepare', 'merge', 'feedback', 'render', 'export', 'clear'):
        sub = subs.add_parser(command)
        sub.add_argument('--history-dir', type=Path, default=Path('.weread-history'))
        if command == 'ingest': sub.add_argument('--input', type=Path, required=True)
        if command in {'prepare', 'merge', 'export'}: sub.add_argument('--output', type=Path, required=True)
        if command == 'export':
            group = sub.add_mutually_exclusive_group()
            group.add_argument('--index', action='store_true', help='Export persistent question index instead of history.')
            group.add_argument('--versions', action='store_true', help='Export captured versions, not independent opinion counts.')
        if command == 'prepare':
            sub.add_argument('--extractions', type=Path)
            sub.add_argument('--max-input-chars', type=int, default=24000)
            sub.add_argument('--max-requests', type=int, default=20)
            sub.add_argument('--max-candidates', type=int, default=200)
            sub.add_argument('--fragment-chars', type=int, default=2000)
            sub.add_argument('--model', default='host-declared')
            sub.add_argument('--cached-output', type=Path)
        if command == 'merge':
            sub.add_argument('--plan', type=Path, required=True)
            sub.add_argument('--results', type=Path, required=True)
        if command in {'feedback', 'render'}: sub.add_argument('--report', type=Path, required=True)
        if command == 'feedback': sub.add_argument('--input', type=Path, required=True)
        if command == 'render':
            sub.add_argument('--output-dir', type=Path, default=Path('weread-reports'))
            sub.add_argument('--format', choices=('both', 'html', 'markdown'), default='both')
        if command == 'clear': sub.add_argument('--confirm-clear', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'clear' and not args.confirm_clear:
            raise ValueError('Explicit --confirm-clear is required')
        # Offline render can use the embedded historical snapshot when its store no longer exists.
        if args.command == 'render':
            report = validate_report(read_json(args.report))
            current = None
            if (args.history_dir / 'history.sqlite3').exists():
                with HistoryStore(args.history_dir) as store: current = store.export()
            write_reports(report, current, args.output_dir, args.format)
        else:
            with HistoryStore(args.history_dir) as store:
                if args.command == 'ingest': store.ingest(read_json(args.input))
                elif args.command == 'export':
                    write_json(args.output, store.problem_index() if args.index else store.export_versions() if args.versions else store.export())
                elif args.command == 'clear': store.clear()
                elif args.command == 'feedback': record_feedback(store, read_json(args.report), read_json(args.input))
                elif args.command == 'prepare':
                    history = store.export()
                    options = dict(max_input_chars=args.max_input_chars, max_requests=args.max_requests, model=args.model)
                    plan = (prepare_comparison(history, read_json(args.extractions), max_candidates=args.max_candidates, **options)
                            if args.extractions else prepare_extraction(history, fragment_chars=args.fragment_chars, **options))
                    write_json(args.output, plan)
                    if args.cached_output: write_json(args.cached_output, cached_results(store, plan))
                elif args.command == 'merge':
                    plan, results = read_json(args.plan), read_json(args.results)
                    merge = merge_extractions if plan['stage'] == 'extract' else merge_comparisons
                    output = merge(store.export(), plan, results)
                    cache_results(store, plan, results)
                    if plan['stage'] == 'extract':
                        complete = set(output['coverage']['complete_version_ids'])
                        store.index_propositions([o for o in output['observations'] if o['version_id'] in complete])
                    write_json(args.output, output)
        return 0
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as exc:
        sys.stderr.write(f'Evolution workflow failed ({type(exc).__name__}); no source text or credentials logged.\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
