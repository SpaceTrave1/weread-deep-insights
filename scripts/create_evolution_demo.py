#!/usr/bin/env python3
"""Fixed, hand-authored synthetic protocol demonstration, not model evaluation."""
from pathlib import Path
import argparse

if __package__:
    from .evaluate_llm import case_data
    from .history import HistoryStore
    from .evidence_bundle import write_json
    from .evolution_analysis import prepare_extraction, merge_extractions, prepare_comparison, merge_comparisons, VERSION
    from .evolution import write_reports
else:
    from evaluate_llm import case_data
    from history import HistoryStore
    from evidence_bundle import write_json
    from evolution_analysis import prepare_extraction, merge_extractions, prepare_comparison, merge_comparisons, VERSION
    from evolution import write_reports


def create_demo(directory):
    directory = Path(directory)
    case = {'id': 'fixed-evolution-demo', 'books': [
        {'title': '虚构阅读手册甲', 'reviews': [{'text': '我认为一本书必须读完，才能算真正理解它。', 'time': '2023-01-01T12:00:00+08:00'}]},
        {'title': '虚构学习手册乙', 'reviews': [{'text': '我开始修正自己的判断：完读不是理解的充分条件，还需要解释与检验。', 'time': '2024-06-01T12:00:00+08:00'}]},
        {'title': '虚构重读手册丙', 'reviews': [{'text': '我仍认为完读不能证明理解，现在还会写下反例，检查自己能否解释关键条件。', 'time': '2025-09-01T12:00:00+08:00'}]},
    ]}
    data = case_data(case)
    for book in data['notebooks']['bookNotes']:
        for i, review in enumerate(book['reviews']): review['reviewId'] = f"fictional-{book['bookId']}-{i}"
    with HistoryStore(directory / 'history') as store:
        store.ingest(data)
        history = store.export()
    plan = prepare_extraction(history, model='fixed-example', provider='hand-authored synthetic demo')
    results = []
    for request in plan['requests']:
        observations = []
        for index, row in enumerate(request['context']['evidence']):
            observations.append({'id': str(index), 'evidence_ids': [row['evidence_id']],
                'question': '读完是否足以证明理解？', 'topic': '阅读与理解', 'subject': '完读与理解的关系',
                'stance': row['text'], 'conditions': '一般阅读学习', 'reason': '按虚构原文记录', 'voice': 'own',
                'quotes': [{'evidence_id': row['evidence_id'], 'text': row['text']}],
                'limitations': ['固定编写的合成示例，不是真实模型分析。']})
        results.append({'schema_version': VERSION, 'stage': 'extract', 'input_digest': request['input_digest'],
                        'status': 'complete', 'processed_evidence_ids': [r['evidence_id'] for r in request['context']['evidence']],
                        'observations': observations, 'abstentions': []})
    extracted = merge_extractions(history, plan, results)
    comparisons = prepare_comparison(history, extracted, model='fixed-example', provider='hand-authored synthetic demo')
    comparison_results = []
    for request in comparisons['requests']:
        candidate = request['context']['candidates'][0]
        rows = {r['version_id']: r for r in request['context']['evidence']}
        support = [rows[v] for v in candidate['version_ids']]
        revision = support[0]['effective_at'].startswith('2023')
        relation = {'candidate_id': candidate['id'], 'relation': 'revision' if revision else 'deepening',
                    'question': candidate['question'],
                    'explanation': ('两条虚构点评表现出对完读与理解关系的修正。' if revision else '后期虚构点评延续判断，并增加反例检验的方法。'),
                    'comparability': dict.fromkeys(('same_question', 'same_subject', 'conditions_compatible', 'own_stance'), True),
                    'quotes': [{'evidence_id': r['evidence_id'], 'text': r['text']} for r in support],
                    'counter_evidence_ids': [], 'limitations': ['固定编写的合成示例，不证明模型准确率。', '旧笔记历史版本未知，日期来自创建时间。']}
        comparison_results.append({'schema_version': VERSION, 'stage': 'compare', 'input_digest': request['input_digest'],
                                   'status': 'complete', 'processed_candidate_ids': [candidate['id']],
                                   'processed_evidence_ids': [r['evidence_id'] for r in request['context']['evidence']],
                                   'relations': [relation], 'abstentions': []})
    report = merge_comparisons(history, comparisons, comparison_results)
    for name, body in (('evolution-extract-plan.json', plan), ('evolution-extract-results.json', results),
                       ('evolution-extractions.json', extracted), ('evolution-compare-plan.json', comparisons),
                       ('evolution-compare-results.json', comparison_results), ('evolution-report.json', report)):
        write_json(directory / name, body)
    return write_reports(report, history, directory, title='合成数据演示：阅读观点演化档案')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('llm-evaluation-results/evolution-demo'))
    args = parser.parse_args(argv)
    for path in create_demo(args.output_dir): print(path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
