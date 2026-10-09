"""Self-contained, escaped Markdown/HTML evidence trajectories."""
import html

if __package__:
    from .evolution_analysis import LABELS, validate_report, normalized
    from .evidence_bundle import digest
    from .evolution_workflow import feedback_view
    from .enhanced_rendering import markdown_text
    from .coverage import coverage_lines
else:
    from evolution_analysis import LABELS, validate_report, normalized
    from evidence_bundle import digest
    from evolution_workflow import feedback_view
    from enhanced_rendering import markdown_text
    from coverage import coverage_lines

TIME_LABELS = {'created_version_unknown': '源创建时间；历史版本未知', 'source_modified': '源修改时间；历史版本未知',
               'observed_edit': '首次观察到本次修改；不代表原创建时间', 'unknown': '时间未知'}
FEEDBACK_LABELS = {'confirmed': '用户确认', 'rejected': '用户否认', 'clarified': '用户补充解释', 'needs_context': '待补充上下文'}
STATUS_LABELS = {'complete': '选中比较范围已声明处理', 'partial': '部分选中比较已声明处理',
                 'not_requested': '尚未收到必要的模型结果', 'abstained': '证据不足，暂不作演化结论'}


def date_label(note):
    return (note['effective_at'] or '日期未知') + '（' + TIME_LABELS[note['time_basis']] + '）'


def group_questions(report, current_history=None):
    groups = {}
    for relation in feedback_view(report, current_history):
        key = normalized(relation['question'])
        if key not in groups:
            groups[key] = {'id': 'question-' + digest([report['history']['dataset_id'], key])[:24],
                           'question': relation['question'], 'relations': [], 'notes': {}}
        group = groups[key]
        group['relations'].append(relation)
        for note in relation['notes']: group['notes'][note['version_id']] = note
    for group in groups.values():
        group['notes'] = sorted(group['notes'].values(), key=lambda n: n['effective_at'] or '~')
    return list(groups.values())


def coverage_text(report):
    c, ex = report['coverage'], report['coverage']['extraction']
    lines = [f"观点抽取：完整声明处理 {ex['complete_notes']}/{ex['available_notes']} 条历史可见笔记；"
             f"片段 {ex['processed_fragments']}/{ex['available_fragments']}。",
             f"候选比较：声明处理 {c['processed_candidates']}/{c['selected_candidates']} 个选中候选；"
             f"检索产生 {c['retrieved_candidates']} 个，同主题潜在配对 {c['possible_within_topic_pairs']} 个。",
             '反证检索仅涵盖每条轨迹列出的提交原文；未提交内容、同义问题及远距离关联可能遗漏。',
             '完整状态仅针对提交范围；结构校验不能证明语义正确，当前未完成独立语义质量验收。']
    sources = sorted({r['provider'] + ' / ' + r['model'] for r in report['plan']['requests']})
    if sources: lines.append('分析来源声明：' + '；'.join(sources) + '。')
    if report['history']['observed_at']: lines.append('报告所用采集快照：' + report['history']['observed_at'])
    coverage = report['history']['collection_coverage']
    return (coverage_lines(coverage) if coverage else ['尚无采集记录。']) + lines


def render_markdown(report, current_history=None, title='我的阅读观点演化档案'):
    validate_report(report)
    groups = group_questions(report, current_history)
    rows = [row for group in groups for row in group['relations']]
    esc = markdown_text
    lines = ['# ' + esc(title), '', '个人点评是立场证据；划线仅补充上下文。以下关系均为候选，用户反馈单独归属。', '']
    lines.extend(esc(s) for s in coverage_text(report))
    lines += ['', f"处理状态：{STATUS_LABELS[report['status']]}。首页精选最多 5 条；证据不足不补齐数量。", '']
    if not rows:
        lines += ['在本次分析范围内未发现足够证据，或尚未收到模型结果；不能据此认定观点没有改变。', '']
    for group in groups:
        lines += ['## 问题档案：' + esc(group['question']), '', '可见表达时间线（含中间节点）：', '']
        lines += ['- ' + esc(date_label(n)) + ' · ' + esc(n['title']) + ' · ' + n['version_id'] for n in group['notes']]
        lines.append('')
    for row in rows:
        lines += [f"### 候选关系：{esc(row['question'])}", '',
                  f"关系：{LABELS[row['relation']]}；轨迹：{row['id']}。", '', esc(row['explanation']), '']
        if row['needs_review']: lines += ['证据版本或模型解释已变化，需要重新核对。', '']
        if row['feedback']:
            feedback = row['feedback']
            lines += [FEEDBACK_LABELS[feedback['status']] + '（用户反馈，不是独立证据）：' + esc(feedback['explanation']), '']
        for f in row['related_feedback']:
            lines += ['相关历史反馈（未自动继承为本次确认）：' + esc(f['explanation']),
                      '当时的模型解释：' + esc(f.get('reviewed_explanation', '未记录')), '']
        for note in sorted(row['notes'], key=lambda n: n['effective_at'] or '~'):
            lines += ['### ' + esc(note['title']), '', '时间：' + esc(date_label(note)),
                      '章节：' + esc(note['chapter'] or '未取得'),
                      '当前可见情况：' + ('本次取得' if note['visibility'] == 'observed' else '本次未取得，不推断删除'),
                      '证据版本：' + note['version_id'], '', '完整个人点评：', '', '> ' + esc(note['text']), '']
        lines += ['支持引文：', '']
        for q in row['quote_sources']:
            lines += ['> ' + esc(q['quote']), '> 来源：' + esc(q['title']) + '；' + q['evidence_id'], '']
        lines += ['反证检索范围：' + ', '.join(row['counter_search_evidence_ids']), '']
        for counter in row['counter_sources']:
            lines += ['反向依据：' + esc(counter['title']) + '；' + counter['evidence_id'], '> ' + esc(counter['text']), '']
        lines += ['局限：' + '；'.join(esc(s) for s in row['limitations']), '']
    lines += ['不作结论：' + esc(s) for s in report['abstentions']]
    return '\n'.join(lines) + '\n'


def render_html(report, current_history=None, title='我的阅读观点演化档案'):
    validate_report(report)
    groups = group_questions(report, current_history)
    rows = [row for group in groups for row in group['relations']]
    esc = lambda s: html.escape(str(s), quote=True)
    parts = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
             '<title>' + esc(title) + '</title><style>body{font:16px/1.75 system-ui,sans-serif;background:#f3f5f9;color:#243047;max-width:1050px;margin:auto;padding:24px}article,header,section{background:white;border-radius:14px;padding:24px;margin:18px 0}blockquote{border-left:4px solid #6384d8;padding:8px 18px;white-space:pre-wrap}small,.muted{color:#5b6780;overflow-wrap:anywhere}summary{cursor:pointer}h1,h2{line-height:1.4}.badge{background:#e8edff;padding:4px 12px;border-radius:16px}.warning{color:#875700}details{margin:12px 0}pre{white-space:pre-wrap}</style><body>',
             '<header><h1>' + esc(title) + '</h1><p>阅读历史 · 观点变化 · 跨书关联</p>',
             '<p>个人点评是立场证据；划线仅补充上下文。模型关系是候选，用户反馈单独归属。</p></header>',
             '<details><summary>数据覆盖、失败统计与分析局限</summary><section>']
    parts += ['<p>' + esc(s) + '</p>' for s in coverage_text(report)]
    parts += ['<p>处理状态：' + esc(STATUS_LABELS[report['status']]) + '。</p></section></details>']
    if not rows:
        parts.append('<section><p>在本次分析范围内未发现足够证据，或尚未收到模型结果；不能据此认定观点没有改变。</p></section>')
    previous = None
    group_index = {row['id']: index for index, group in enumerate(groups) for row in group['relations']}
    for row in rows:
        index = group_index[row['id']]
        if index != previous:
            if index == 5: parts.append('<details><summary>展开其他候选问题档案</summary>')
            group = groups[index]
            parts.append('<section id="' + esc(group['id']) + '"><h2>问题档案：' + esc(group['question']) + '</h2><ol>')
            for n in group['notes']:
                parts.append('<li>' + esc(date_label(n)) + ' · ' + esc(n['title']) + '</li>')
            parts.append('</ol><p>按可用时间排序；包含中间节点，未将同一笔记编辑当作独立表达。</p></section>')
            previous = index
        parts += ['<article id="' + esc(row['id']) + '"><h2>' + esc(row['question']) + '</h2>',
                  '<span class="badge">' + LABELS[row['relation']] + '</span><p>' + esc(row['explanation']) + '</p>']
        if row['needs_review']: parts.append('<p class="warning">证据版本或模型解释已变化，需要重新核对。</p>')
        if row['feedback']:
            f = row['feedback']
            parts.append('<p><b>' + FEEDBACK_LABELS[f['status']] + '（用户反馈，不是独立证据）</b>：' + esc(f['explanation']) + '</p>')
        for f in row['related_feedback']:
            parts.append('<p class="muted">相关历史反馈（未自动继承为本次确认）：' + esc(f['explanation']) + '</p><p class="muted">当时的模型解释：' + esc(f.get('reviewed_explanation', '未记录')) + '</p>')
        for note in sorted(row['notes'], key=lambda n: n['effective_at'] or '~'):
            parts += ['<section><h3>' + esc(note['title']) + '</h3><p>' + esc(date_label(note)) + '</p>',
                      '<p class="muted">章节：' + esc(note['chapter'] or '未取得') + '；' + esc(note['version_id']) + '</p>',
                      '<p class="muted">' + ('本次取得' if note['visibility'] == 'observed' else '本次未取得，不推断删除') + '</p>',
                      '<details><summary>展开完整个人点评</summary><blockquote>' + esc(note['text']) + '</blockquote></details></section>']
        for q in row['quote_sources']:
            parts.append('<blockquote>' + esc(q['quote']) + '<footer><small>' + esc(q['title']) + '；' + esc(q['evidence_id']) + '</small></footer></blockquote>')
        parts.append('<details><summary>反证及检索范围</summary><p class="muted">' + esc(', '.join(row['counter_search_evidence_ids'])) + '</p>')
        for c in row['counter_sources']:
            parts.append('<p>' + esc(c['title']) + '</p><blockquote>' + esc(c['text']) + '</blockquote>')
        parts += ['</details><p class="muted">局限：' + esc('；'.join(row['limitations'])) + '</p>',
                  '<small>反馈可通过当前 Agent 或 evolution.py feedback 保存；离线页面只展示已保存反馈。</small></article>']
    if len(groups) > 5: parts.append('</details>')
    parts += ['<p>' + esc(s) + '</p>' for s in report['abstentions']]
    return ''.join(parts) + '</body></html>\n'
