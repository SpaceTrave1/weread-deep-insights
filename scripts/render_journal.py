#!/usr/bin/env python3
"""Combine existing private outputs into an offline reading journal. No credentials/network."""
import argparse
import copy
import sys
from pathlib import Path

if __package__:
    from .evidence_bundle import validate_bundle, read_json
    from .llm_analysis import attach_insights
    from .journal_rendering import render_journal, date
    from .rendering import render_markdown
    from .evolution_rendering import render_markdown as evolution_markdown
    from .evolution_analysis import validate_report, validate_history
else:
    from evidence_bundle import validate_bundle, read_json
    from llm_analysis import attach_insights
    from journal_rendering import render_journal, date
    from rendering import render_markdown
    from evolution_rendering import render_markdown as evolution_markdown
    from evolution_analysis import validate_report, validate_history


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='Existing validated baseline evidence bundle')
    parser.add_argument('--semantic-input', type=Path, help='Original bundle bound to the model result; defaults to --input')
    parser.add_argument('--analysis-result', type=Path, help='Existing model result; never invokes a model')
    parser.add_argument('--evolution-report', type=Path)
    parser.add_argument('--history-input', type=Path, help='Masked history export; no database mutation')
    parser.add_argument('--basis-input', type=Path, help='Optional newer basis/annual/coverage, bound to --history-input')
    parser.add_argument('--context-input', type=Path, help='Optional entity-keyed book context; background only')
    parser.add_argument('--output-dir', type=Path, default=Path('weread-reports/reading-journal'))
    parser.add_argument('--format', choices=['html','markdown','both'], default='both')
    args = parser.parse_args(argv)
    if args.semantic_input and not args.analysis_result:
        parser.error('--semantic-input requires --analysis-result')
    if args.basis_input and not args.history_input:
        parser.error('--basis-input requires --history-input')
    try:
        bundle = validate_bundle(read_json(args.input))
        report = copy.deepcopy(bundle['baseline_report'])
        if args.analysis_result:
            semantic_bundle = validate_bundle(read_json(args.semantic_input)) if args.semantic_input else bundle
            output = read_json(args.analysis_result)
            result, trace = (output['result'],output['trace']) if isinstance(output,dict) and set(output)=={'result','trace'} else (output,{})
            # Validate against the exact submitted selection, not the broad baseline.
            report['llmAnalysis'] = attach_insights(semantic_bundle,result,trace=trace)['llmAnalysis']
            report['semanticGeneratedAt'] = semantic_bundle['baseline_report']['generatedAt']
        history = validate_history(read_json(args.history_input)) if args.history_input else None
        evolution = validate_report(read_json(args.evolution_report)) if args.evolution_report else None
        basis = read_json(args.basis_input) if args.basis_input else None
        contexts = read_json(args.context_input) if args.context_input else {}
        # Build both before touching output files; validate even Markdown-only runs.
        rendered = render_journal(report,evidence=bundle['evidence'],history=history,evolution=evolution,current_basis=basis,contexts=contexts)
        md_report = copy.deepcopy(report)
        if basis:
            md_report.update(basis=basis['basis'],annual=basis['annual'],coverage=basis['coverage'])
        markdown = (f'统计快照：{date(history["observed_at"] if basis else report["generatedAt"])}；'
                    f'分类、规则及原报告建议快照：{date(report["generatedAt"])}。\n\n') + render_markdown(md_report)
        if evolution:
            markdown += '\n\n' + evolution_markdown(evolution,history,title='我的思考：时间视图')
    except (ValueError,OSError,KeyError,TypeError,IndexError,AttributeError) as exc:
        sys.stderr.write(f'Journal rendering failed ({type(exc).__name__}); no report written.\n')
        return 2
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for name,content in [('index.html',rendered),('weread_deep_report.md',markdown)]:
        if args.format=='both' or args.format==('html' if name.endswith('.html') else 'markdown'):
            path=args.output_dir/name
            path.write_text(content,encoding='utf-8')
            print(path.resolve())
    return 0


if __name__=='__main__':
    raise SystemExit(main())
