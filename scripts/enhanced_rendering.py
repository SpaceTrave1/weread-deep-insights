"""Render verified references and unverified semantic interpretations safely."""
import html
import re

LABELS = {"theme": "语义主题", "question": "问题意识", "stance": "点评立场", "connection": "跨书联系",
          "change": "表达变化", "portrait": "阅读倾向", "suggestion": "可选建议"}


def markdown_text(value):
    # Keep model text as text: disable HTML, Markdown links/images and line injection.
    escaped = html.escape(str(value), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#!|>])", r"\\\1", escaped).replace("\n", " ").replace("\r", " ")


def coverage_text(analysis):
    c = analysis['coverage']
    return (f"模型分析范围：声明处理 {c['declared_fragments']}/{c['selected_fragments']} 个选中片段；"
            f"完整涵盖 {c['declared_complete_notes']}/{c['selected_notes']} 条选中笔记，"
            f"本次可用正文共 {c['available_notes']} 条。与 API 采集覆盖分别计算。")


def semantic_markdown(analysis):
    lines = ['## 大模型语义分析', '', coverage_text(analysis), '', markdown_text(analysis['notice']), '']
    result = analysis['result']
    if result is None:
        lines.extend(['增强分析未完成，已保留本地规则报告。', markdown_text(analysis['failure'] or '模型结果不可用。'), ''])
    else:
        lines.extend([f"来源：{markdown_text(result['provider'])}；模型：{markdown_text(result['model'])}；状态：{result['status']}。", ''])
        evidence = {row['evidence_id']: row for row in analysis['evidence']}
        for claim in result['claims']:
            lines.extend([f"### {LABELS[claim['category']]}：{markdown_text(claim['statement'])}", '',
                          f"范围：{'本次样本' if claim['scope'] == 'sample' else '所引片段'}。", '',
                          f"推断依据：{markdown_text(claim['rationale'])}", ''])
            for quote in claim['quotes']:
                row = evidence[quote['evidence_id']]
                lines.extend([f"> {markdown_text(quote['text'])}",
                    f"> 来源：{markdown_text(row['title'])}，{'个人点评' if row['kind'] == 'personal_review' else '原文划线'}；证据 {row['evidence_id']}。", ''])
            lines.append('支持证据：' + ', '.join(claim['evidence_ids']))
            if claim['counter_evidence_ids']:
                lines.append('反向证据：' + ', '.join(claim['counter_evidence_ids']))
            lines.extend(['', '局限：' + '；'.join(markdown_text(s) for s in claim['limitations']), ''])
        for reason in result['abstentions']:
            lines.extend(['不作结论：' + markdown_text(reason), ''])
    trace = analysis['trace']
    if trace:
        lines.extend([f"调用记录：请求尝试 {trace.get('calls', 0)}，缓存命中 {trace.get('cache_hits', 0)}；"
                      f"接口返回用量累计：输入 {trace.get('reported_input_tokens', 0)}、输出 {trace.get('reported_output_tokens', 0)} tokens。"
                      "缺少用量字段时无法计入，不保证涵盖失败请求费用。", ''])
        if 'extraction_declared_fragments' in trace:
            lines.extend([f"分块声明处理 {trace['extraction_declared_fragments']} 个片段；最终综合声明处理 {trace['synthesis_declared_fragments']} 个片段。", ''])
        for warning in trace.get('warnings', []):
            lines.extend(['处理说明：' + markdown_text(warning), ''])
    lines.extend(['## 本地规则参考', '', '以下保留可复现统计和规则结果；与模型语义结论分开呈现。', ''])
    return '\n'.join(lines)


def semantic_html(analysis):
    escape = lambda text: html.escape(str(text))
    parts = ['<section id="llm-analysis" class="section featured"><h2>大模型语义分析</h2>',
             f'<p>{escape(coverage_text(analysis))}</p>', f'<p class="muted">{escape(analysis["notice"])}</p>']
    result = analysis['result']
    if result is None:
        parts.append(f'<p>增强分析未完成，已保留本地规则报告。{escape(analysis["failure"] or "模型结果不可用。")}</p>')
    else:
        parts.append(f'<p>来源：{escape(result["provider"])}；模型：{escape(result["model"])}；状态：{escape(result["status"])}。</p>')
        evidence = {row['evidence_id']: row for row in analysis['evidence']}
        for claim in result['claims']:
            parts.extend([f'<article><h3>{LABELS[claim["category"]]}：{escape(claim["statement"])}</h3>',
                          f'<p>范围：{"本次样本" if claim["scope"] == "sample" else "所引片段"}。</p>',
                          f'<p>推断依据：{escape(claim["rationale"])}</p>'])
            for quote in claim['quotes']:
                row = evidence[quote['evidence_id']]
                kind = '个人点评' if row['kind'] == 'personal_review' else '原文划线'
                parts.append(f'<blockquote><p>{escape(quote["text"])}</p><footer>{escape(row["title"])}，{kind}；证据 {escape(row["evidence_id"])}</footer></blockquote>')
            parts.append(f'<p class="muted">支持证据：{escape(", ".join(claim["evidence_ids"]))}</p>')
            if claim['counter_evidence_ids']:
                parts.append(f'<p class="muted">反向证据：{escape(", ".join(claim["counter_evidence_ids"]))}</p>')
            parts.append(f'<p class="muted">局限：{escape("；".join(claim["limitations"]))}</p></article>')
        for reason in result['abstentions']:
            parts.append(f'<p>不作结论：{escape(reason)}</p>')
    if analysis['trace']:
        trace = analysis['trace']
        parts.append(f'<p class="muted">请求尝试 {trace.get("calls", 0)}；缓存命中 {trace.get("cache_hits", 0)}。接口返回输入/输出用量累计 {trace.get("reported_input_tokens", 0)}/{trace.get("reported_output_tokens", 0)} tokens；缺失字段或失败请求费用可能未包含。</p>')
        if 'extraction_declared_fragments' in trace:
            parts.append(f'<p class="muted">分块声明处理 {trace["extraction_declared_fragments"]} 个片段；最终综合声明处理 {trace["synthesis_declared_fragments"]} 个片段。</p>')
        parts.extend(f'<p class="muted">处理说明：{escape(warning)}</p>' for warning in trace.get('warnings', []))
    parts.append('</section><h2>本地规则参考</h2><p>以下规则结果与模型语义结论分开呈现。</p>')
    return '\n'.join(parts)
