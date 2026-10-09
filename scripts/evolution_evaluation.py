#!/usr/bin/env python3
"""Prepare invented host evaluations; score separately supplied human reviews."""
import argparse
import math
import sys
from pathlib import Path

if __package__:
    from .evaluate_llm import case_data
    from .history import HistoryStore
    from .evidence_bundle import write_json, read_json
    from .evolution_analysis import prepare_extraction, require
else:
    from evaluate_llm import case_data
    from history import HistoryStore
    from evidence_bundle import write_json, read_json
    from evolution_analysis import prepare_extraction, require


def synthetic_cases():
    # Template variants share a family. Report them as correlated synthetic scenarios,
    # not independent samples of real users. Gold labels never enter host requests.
    families = {
        'development': [
            ('finish', '完读是否代表理解', '我认为必须读完才算理解。', '我不再把完读当成理解证明，需要检验解释。', True),
            ('effort', '努力如何影响结果', '我认为努力足以保证结果。', '我修正了这个判断：努力必要，但资源与时机也会影响结果。', True),
            ('practice', '练习需要反馈吗', '我认为重复练习就足够了。', '我现在认为重复需要反馈，否则也会巩固错误。', True),
            ('memory', '记忆是否可靠', '我相信自己的回忆准确。', '我不再把清晰回忆等同事实，开始核对当时记录。', True),
            ('speed', '学习速度是否应优先', '我认为学习越快越好。', '我改变了看法：需要留出解释和验证的时间。', True),
            ('plan', '计划是否应固定', '我认为好计划必须坚持不变。', '我认为新证据出现时应该修改计划。', True),
            ('expert', '专家建议是否可直接采用', '我认为专家建议可以直接套用。', '我现在先核对建议适用的条件。', True),
            ('condition', '效率如何评价', '紧急救援时，我支持集中协调。', '探索新方法时，我支持分散试验。', False),
            ('quote', '失败如何理解', '作者说“失败毫无价值”，我在转述这一句。', '我认为复盘失败可以提供信息。', False),
            ('irony', '忙碌是否代表成长', '“越忙越有成长”，真是方便的自我安慰。我并不认同。', '我仍认为需要检查忙碌的实际结果。', False),
        ],
        'holdout': [
            ('metrics', '指标能否代表目标', '我认为提高指标就等于实现目标。', '我不再这么看，指标被优化后可能偏离原目标。', True),
            ('reading', '阅读是否必须逐字进行', '我认为任何书都应逐字阅读。', '我现在认为阅读方式应随问题调整，不必每本逐字读。', True),
            ('competition', '竞争是否总有好处', '我认为竞争总会改善结果。', '我不再赞成“总会”，过度竞争也可能破坏合作。', True),
            ('argument', '争论的目的是什么', '我认为争论首先要赢。', '我改变了看法，先找到分歧和可检验的依据更重要。', True),
            ('simplicity', '解释是否越简单越好', '我认为越简单的解释就越正确。', '我修正为：简洁有价值，但不能忽略反例。', True),
            ('reread', '重读是否有必要', '我认为重读只是浪费时间。', '我现在发现带着新问题重读能发现先前遗漏的条件。', True),
            ('uncertainty', '不确定是否应被消除', '我认为做判断前必须消除所有不确定。', '我不再要求全部消除，改为标明不确定并寻找可逆行动。', True),
            ('continuity', '证据如何核对', '我认为重要判断需要原始证据。', '我仍坚持重要判断需要原始证据。', False),
            ('extension', '对照方法如何使用', '我赞成在学习中用对照检查解释。', '我把对照方法用于园艺观察，原来的判断仍适用。', False),
            ('unknown-time', '笔记如何组织', '我认为笔记应按书整理。', '我更倾向按问题整理。', False),
        ],
    }
    cases = []
    for split, templates in families.items():
        for family, question, before, after, changed in templates:
            for variant in range(3):
                key = f'{split}-{family}-{variant}'
                reviews = [{'text': before + f'（虚构记录组 {variant}）', 'time': '2023-02-01T12:00:00+08:00'},
                           {'text': after + f'（虚构记录组 {variant}）', 'time': '2025-04-01T12:00:00+08:00'}]
                if family == 'unknown-time':
                    for r in reviews: r['time'] = None
                books = ([{'title': '虚构重读手册', 'reviews': reviews}] if family == 'reread' else
                         [{'title': f'虚构问题手册{variant}-{i}', 'reviews': [r]} for i, r in enumerate(reviews)])
                cases.append({'id': key, 'split': split, 'family': family, 'synthetic': True,
                              'books': books, 'question': question, 'expected_change': changed,
                              'rubric': ['核对本人立场、判断对象和条件。',
                                         '该案例预期' + ('支持修正或反转候选。' if changed else '不应认定修正或反转。'),
                                         '时间、引用及反证须回到原文；模板变体不是独立用户。']})
    return cases


def summarize(sheet):
    require(isinstance(sheet, dict) and isinstance(sheet.get('cases'), list), 'Invalid manual review sheet')
    predicted = reviewed = supported = gold = found = 0
    all_discovery = True
    seen = set()
    for case in sheet['cases']:
        require(isinstance(case, dict) and isinstance(case.get('id'), str) and case['id'] not in seen, 'Duplicate/invalid case')
        seen.add(case['id'])
        require(type(case.get('expected_change')) is bool and type(case.get('discovery_reviewed')) is bool, 'Invalid case labels')
        all_discovery &= case['discovery_reviewed']
        gold += case['expected_change']
        require(isinstance(case.get('predictions'), list), 'Invalid predictions')
        matches = False
        for row in case['predictions']:
            require(isinstance(row, dict) and row.get('relation') in {'continuity', 'deepening', 'extension', 'revision', 'reversal', 'tension'}, 'Invalid relation review')
            require(row.get('supported') is None or type(row['supported']) is bool, 'Invalid support label')
            require(row.get('matches_gold') is None or type(row['matches_gold']) is bool, 'Invalid matching label')
            if row['relation'] in {'revision', 'reversal'}:
                predicted += 1
                if row.get('supported') is not None:
                    reviewed += 1
                    supported += row['supported']
                matches |= row.get('matches_gold') is True and row.get('supported') is True
        found += case['expected_change'] and matches
    precision = supported / reviewed if reviewed else None
    interval = None
    if reviewed:
        z = 1.96
        center = (precision + z * z / (2 * reviewed)) / (1 + z * z / reviewed)
        width = z * math.sqrt(precision * (1 - precision) / reviewed + z * z / (4 * reviewed * reviewed)) / (1 + z * z / reviewed)
        interval = [max(0, center - width), min(1, center + width)]
    passed = (sheet.get('split') == 'holdout' and sheet.get('review_source') == 'human-declared'
              and predicted >= 20 and predicted == reviewed and all_discovery and precision is not None and precision >= .9)
    return {'schema_version': 'evolution-evaluation-1.0', 'predicted_changes': predicted, 'reviewed_changes': reviewed,
            'supported_changes': supported, 'unreviewed_changes': predicted - reviewed, 'precision': precision,
            'precision_wilson_95': interval, 'expected_change_cases': gold, 'found_change_cases': found,
            'recall_by_case': found / gold if gold and all_discovery else None,
            'semantic_pass': bool(passed), 'minimum_reviewed_changes': 20, 'precision_target': .9,
            'notice': 'Reviewer attribution is declared, not audited. Synthetic family variants are correlated; this is not real-user accuracy.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['prepare', 'score'], default='prepare')
    parser.add_argument('--split', choices=['development', 'holdout'], default='development')
    parser.add_argument('--output-dir', type=Path, default=Path('llm-evaluation-results/evolution'))
    parser.add_argument('--reviews', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.mode == 'score':
            require(args.reviews is not None, 'Score requires independent manual reviews')
            write_json(args.output_dir / 'metrics.json', summarize(read_json(args.reviews)))
        else:
            sheet = {'split': args.split, 'review_source': 'unreviewed', 'cases': []}
            for case in synthetic_cases():
                if case['split'] != args.split: continue
                directory = args.output_dir / case['id']
                data = case_data(case)
                for book in data['notebooks']['bookNotes']:
                    for i, review in enumerate(book['reviews']): review['reviewId'] = f"fictional-{book['bookId']}-{i}"
                with HistoryStore(directory / 'history') as store:
                    store.ingest(data)
                    write_json(directory / 'extract-requests.json', prepare_extraction(store.export()))
                sheet['cases'].append({'id': case['id'], 'family': case['family'], 'expected_change': case['expected_change'],
                                       'discovery_reviewed': False, 'predictions': [], 'rubric': case['rubric']})
            write_json(args.output_dir / 'review-sheet.json', sheet)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        sys.stderr.write(f'Evaluation failed ({type(exc).__name__}).\n')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
