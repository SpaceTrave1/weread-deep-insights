#!/usr/bin/env python3
"""Prepare synthetic evaluations offline; real model runs require explicit consent."""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

if __package__:
    from .evidence_bundle import prepare_bundle, read_json, write_json
    from .llm_analysis import plan_requests
    from .analyze_bundle import add_model_args, client_from_args, run_analysis
else:
    from evidence_bundle import prepare_bundle, read_json, write_json
    from llm_analysis import plan_requests
    from analyze_bundle import add_model_args, client_from_args, run_analysis

CASES_PATH = Path(__file__).resolve().parents[1] / 'tests/fixtures/semantic_cases.json'


def case_data(case):
    notebooks, notes, shelf = [], [], []
    for index, book in enumerate(case['books']):
        key = f"synthetic-{case['id']}-{index}"
        reviews = [{'content': row['text'], 'createTime': row.get('time')} for row in book.get('reviews', [])]
        underlines = [{'text': text} for text in book.get('underlines', [])]
        meta = {'bookId': key, 'title': book['title'], 'author': '合成作者'}
        shelf.append(meta)
        notebooks.append({'bookId': key, 'book': meta, 'reviewCount': len(reviews),
                          'noteCount': len(underlines), 'bookmarkCount': 0})
        notes.append({'bookId': key, 'title': book['title'], 'author': '合成作者',
                      'reviews': reviews, 'underlines': underlines,
                      'reviewCount': len(reviews), 'underlineCount': len(underlines),
                      'totalNotes': len(reviews) + len(underlines),
                      'fetchStatus': {'reviews': 'success' if reviews else 'empty',
                                      'underlines': 'success' if underlines else 'empty'}})
    return {'generatedAt': '2026-01-01T00:00:00+08:00',
            'stats': {'overall': {}, 'weekly': {}, 'monthly': {}, 'annual': []},
            'shelf': {'raw': {}, 'books': shelf, 'albums': [], 'progress': [], 'bookInfo': []},
            'notebooks': {'books': notebooks, 'bookNotes': notes},
            'limits': {'maxNoteBooks': None, 'skipProgress': True, 'skipBookInfo': True},
            'collectionStatus': {'overall': 'empty', 'weekly': 'empty', 'monthly': 'empty',
                                 'shelf': 'success' if shelf else 'empty', 'notebooks': 'success' if notes else 'empty'}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=CASES_PATH)
    parser.add_argument('--output-dir', type=Path, default=Path('llm-evaluation-results'))
    parser.add_argument('--mode', choices=['prepare', 'api'], default='prepare')
    parser.add_argument('--split', choices=['all', 'development', 'holdout'], default='all')
    add_model_args(parser)
    args = parser.parse_args(argv)
    try:
        dataset = read_json(args.cases)
        if not isinstance(dataset, dict) or dataset.get('schema_version') != '1.0' or dataset.get('synthetic') is not True:
            raise ValueError("Evaluation requires an explicitly synthetic dataset")
        cases = dataset['cases']
        if not isinstance(cases, list):
            raise ValueError("Invalid evaluation cases")
        client = client_from_args(args) if args.mode == 'api' else None
        evaluations = []
        seen = set()
        for case in cases:
            if not isinstance(case, dict) or not isinstance(case.get('id'), str) or not re.fullmatch(r'[a-z0-9-]{1,80}', case['id']) or case['id'] in seen:
                raise ValueError("Invalid or duplicate evaluation case ID")
            seen.add(case['id'])
            if args.split != 'all' and case['split'] != args.split:
                continue
            bundle = prepare_bundle(case_data(case), '合成评测：' + case['id'])
            directory = args.output_dir / case['id']
            write_json(directory / 'bundle.json', bundle)
            item = {'id': case['id'], 'split': case['split'], 'mode': args.mode,
                    'manual_rubric': case['rubric'], 'semantic_support': None, 'theme_quality': None,
                    'manual_review_required': True, 'rule_themes': [t['name'] for t in bundle['baseline_report']['themes']]}
            if client is None:
                write_json(directory / 'requests.json', {'requests': plan_requests(bundle, args.llm_max_input_chars)})
                item['status'] = 'prepared'
            else:
                started = time.monotonic()
                calls_before = client.trace['calls']
                try:
                    output = run_analysis(bundle, client)
                    write_json(directory / 'insights.json', output)
                    item.update(status=output['result']['status'], structurally_valid=True,
                                claim_count=len(output['result']['claims']),
                                analyzed_fragments=len(output['result']['analyzed_evidence_ids']))
                except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
                    item.update(status='failed', structurally_valid=False, failure_type=type(exc).__name__)
                item.update(elapsed_seconds=round(time.monotonic() - started, 3),
                            request_attempts=client.trace['calls'] - calls_before)
            evaluations.append(item)
        write_json(args.output_dir / 'evaluation.json', {'synthetic': True, 'cases': evaluations,
            'notice': 'Schema/citation checks are not semantic grades. Fill manual review fields after inspecting original evidence.',
            'trace': client.trace if client else {}})
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"Evaluation failed ({type(exc).__name__}).\n")
    print((args.output_dir / 'evaluation.json').resolve())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
