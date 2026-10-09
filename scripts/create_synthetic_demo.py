#!/usr/bin/env python3
"""Reproducible authored demonstration, not a live model quality evaluation."""
import argparse
from pathlib import Path

if __package__:
    from .evaluate_llm import CASES_PATH, case_data
    from .evidence_bundle import read_json, prepare_bundle, write_json
    from .llm_analysis import attach_insights
    from .rendering import render_markdown, render_html
else:
    from evaluate_llm import CASES_PATH, case_data
    from evidence_bundle import read_json, prepare_bundle, write_json
    from llm_analysis import attach_insights
    from rendering import render_markdown, render_html


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('llm-evaluation-results/demo'))
    args = parser.parse_args(argv)
    case = read_json(CASES_PATH)['cases'][0]
    bundle = prepare_bundle(case_data(case), '合成示例：大模型增强阅读报告')
    rows = bundle['evidence']
    result = {'schema_version': '1.0', 'prompt_version': '1.0', 'input_digest': bundle['input_digest'],
              'provider': 'synthetic-demo', 'model': 'authored-example', 'status': 'complete',
              'analyzed_evidence_ids': [row['evidence_id'] for row in rows],
              'claims': [{'id': 'gardening-observation', 'category': 'theme', 'scope': 'sample',
                  'statement': '园艺观察与对照试验：两条点评都把植物养护问题落到可比较的条件。',
                  'evidence_ids': [row['evidence_id'] for row in rows],
                  'quotes': [{'evidence_id': row['evidence_id'], 'text': row['text'][:100]} for row in rows],
                  'rationale': '一条点评记录光照和浇水间隔，另一条比较土壤保水性；共同线索是用观察与对照校准解释。',
                  'counter_evidence_ids': [],
                  'limitations': ['仅有两条合成点评，不能确认专业能力、稳定习惯或完整兴趣分布。']}],
              'abstentions': ['画像与长期变化证据不足；不推断人格、实际行动或信息茧房。']}
    report = attach_insights(bundle, result)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / 'bundle.json', bundle)
    write_json(args.output_dir / 'insights.json', result)
    (args.output_dir / 'weread_deep_report.md').write_text(render_markdown(report), encoding='utf-8')
    template = Path(__file__).resolve().parents[1] / 'assets/report-template.html'
    html_path = args.output_dir / 'weread_deep_report.html'
    html_path.write_text(render_html(report, template), encoding='utf-8')
    print(html_path.resolve())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
