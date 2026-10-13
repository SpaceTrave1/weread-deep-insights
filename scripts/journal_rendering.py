"""Offline editorial reading journal. Facts, interpretations and dates stay separate."""
from __future__ import annotations

import html
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__:
    from .coverage import coverage_lines
    from .evolution_analysis import validate_report, validate_history, LABELS
    from .evolution_rendering import group_questions, TIME_LABELS, FEEDBACK_LABELS, coverage_text
    from .enhanced_rendering import LABELS as SEMANTIC_LABELS
else:
    from coverage import coverage_lines
    from evolution_analysis import validate_report, validate_history, LABELS
    from evolution_rendering import group_questions, TIME_LABELS, FEEDBACK_LABELS, coverage_text
    from enhanced_rendering import LABELS as SEMANTIC_LABELS

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
CN = timezone(timedelta(hours=8))
MODULES = [('overview', '阅读总览', '一份持续生长的阅读记录'),
           ('map', '阅读地图', '时间、书籍与阅读的重心'),
           ('notes', '笔记与表达', '回到你留下的每一句话'),
           ('thinking', '我的思考', '在主题与时间之间，理解自己'),
           ('inspiration', '阅读启发', '为下一次阅读，留一个问题')]


def esc(value):
    return html.escape(str(value), quote=True)


def json_script(value):
    # Even JSON script blocks are terminated by an HTML </script> sequence.
    return json.dumps(value, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')


def date(value):
    if not value:
        return '日期未知'
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo:
            parsed = parsed.astimezone(CN)
        return parsed.strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return '日期未知'


def heading(number, title, subtitle):
    return f'<header class="page-heading"><p class="eyebrow">READING JOURNAL / {number:02}</p><h1>{esc(title)}</h1><p class="lead">{esc(subtitle)}</p></header>'


def source_line(label, snapshot):
    return f'<p class="source-line"><i></i>{esc(label)} · 快照 {date(snapshot)}</p>'


def quote_html(row):
    return f'<blockquote class="evidence-quote">{esc(row.get("text", ""))}<cite>{esc(row.get("title", ""))} · {esc(row.get("kind", "证据"))}</cite></blockquote>'


def rank_list(rows, value, unit='', maximum=None):
    maximum = maximum or max((float(r.get(value) or 0) for r in rows), default=1) or 1
    return ''.join(f'<div class="rank-row"><span class="rank-num">{i+1:02}</span><div><div class="rank-label"><b>{esc(r.get("name", r.get("title", "")))}</b><span>{esc(r.get(value, 0))}{esc(unit)}</span></div><div class="track"><span style="width:{min(100,max(0,float(r.get(value) or 0)/maximum*100)):.2f}%"></span></div></div></div>' for i, r in enumerate(rows))


def note_library(history, evidence):
    if history:
        # Only the latest visible version per entity; missing records are not deletion.
        latest = {}
        for note in history['notes']:
            key = note['entity_id']
            if key not in latest or (note.get('last_snapshot', ''), note.get('first_observed_at', '')) > (latest[key].get('last_snapshot', ''), latest[key].get('first_observed_at', '')):
                latest[key] = note
        return [dict(title=n['title'], author=n.get('author', ''), text=n['text'], chapter=n.get('chapter', ''),
                     kind=n['kind'], date=date(n.get('effective_at')), time_basis=TIME_LABELS.get(n.get('time_basis'), '时间来源未知'),
                     version=n['version_id'], visibility=n.get('visibility', 'unknown')) for n in latest.values()]
    # Bundle fragments are not silently counted as independent whole notes.
    grouped = {}
    for row in evidence:
        key = (row['book_ref'], row['kind'], row['source_ref'])
        grouped.setdefault(key, []).append(row)
    return [dict(title=rows[0]['title'], author=rows[0].get('author', ''),
                 text=''.join(r['text'] for r in sorted(rows, key=lambda r:r['fragment_index'])),
                 chapter=rows[0].get('chapter', ''), kind=rows[0]['kind'], date=date(rows[0].get('time')),
                 time_basis='证据包记录的源时间；版本历史未知', version=rows[0]['source_ref'], visibility='observed')
            for rows in grouped.values()]


def timeline_groups(evolution, history, contexts):
    groups = group_questions(evolution, history) if evolution else []
    topic_by_candidate = {c['id']:c['topic'] for r in evolution['plan']['requests'] for c in r['context']['candidates']} if evolution else {}
    parts, themes, feedback = [], [], {}
    for index, group in enumerate(groups):
        topic = topic_by_candidate.get(group['relations'][0]['candidate_id'], '问题档案')
        books = list(dict.fromkeys(n['title'] for n in group['notes']))
        types = sorted({r['relation'] for r in group['relations']})
        notes = group['notes']
        preview = group['relations'][0]
        # This is a theme lens on already proposed relationships, not new model analysis.
        themes.append(f'<article class="question-card" data-types="{esc(" ".join(types))}"><p class="eyebrow">QUESTION {index+1:02} / {esc(topic)}</p><h3>{esc(group["question"])}</h3><p>{esc(preview["explanation"])}</p><div class="book-tags">'+''.join(f'<span>{esc(b)}</span>' for b in books)+f'</div><div class="question-foot"><span>{len(notes)} 条来源 · {len(group["relations"])} 项关系候选</span><button class="text-button" data-open-archive="{esc(group["id"])}">沿时间展开 <span aria-hidden="true">↗</span></button></div></article>')
        nodes = []
        for note in notes:
            background = contexts.get(note['entity_id'], {}).get('abstract', '')
            context = f'<div class="book-context"><span>书中原文 · 接口附着节选，仅作背景</span><p>{esc(background[:450])}{"…" if len(background)>450 else ""}</p></div>' if background else '<p class="small">未取得对应的书中原文。</p>'
            nodes.append(f'<div class="timeline-node"><div class="node-date"><b>{date(note["effective_at"])}</b><span>{esc(TIME_LABELS[note["time_basis"]])}</span></div><div class="node-body"><h4>{esc(note["title"])}</h4><p class="small">{esc(note["chapter"] or "章节未取得")}</p><blockquote>{esc(note["text"][:150])}{"…" if len(note["text"])>150 else ""}</blockquote><details class="original"><summary>完整点评与上下文</summary><p class="full-note">{esc(note["text"])}</p>{context}<p class="source-id">原文版本 {esc(note["version_id"])}</p></details></div></div>')
        relations = []
        for row in group['relations']:
            saved = row['feedback']
            state = FEEDBACK_LABELS[saved['status']] if saved else '待你确认'
            warning = '<p class="review-warning">来源版本或解释已变化，需要重新核对。</p>' if row['needs_review'] else ''
            saved_html = '<p class="small">用户反馈：'+esc(saved['explanation'])+'</p>' if saved else ''
            related_html = ''.join('<p class="small">相关历史反馈，未继承为本次确认：'+esc(f['explanation'])+'</p>' for f in row['related_feedback'])
            # The trajectory fingerprint binds question, source versions and explanation.
            # Keep the existing evolution.py feedback input contract exactly.
            feedback[row['id']] = {'trajectory_id':row['id']}
            counter = ''.join(f'<blockquote>{esc(c["text"])}<cite>{esc(c["title"])}</cite></blockquote>' for c in row['counter_sources'])
            relations.append(f'<details class="comparison" data-relation="{esc(row["relation"])}"><summary><span class="badge {esc(row["relation"])}">{LABELS[row["relation"]]}</span><span>{date(row["notes"][0]["effective_at"])} → {date(row["notes"][-1]["effective_at"])}</span><span class="pending">{esc(state)}</span></summary><div class="comparison-body">{warning}<p>{esc(row["explanation"])}</p><div class="comparison-quotes">'+''.join(f'<blockquote>{esc(q["quote"])}<cite>{esc(q["title"])}</cite></blockquote>' for q in row['quote_sources'])+f'</div><details class="limits"><summary>反向证据与解释边界</summary>{counter}<p>{esc("；".join(row["limitations"]))}</p><p>反证检索声明涉及 {len(row["counter_search_evidence_ids"])} 个提交片段，未提交记录不算已经检查。</p></details>{saved_html}{related_html}<div class="feedback" data-trajectory="{esc(row["id"])}"><label>你的看法<select aria-label="反馈状态"><option value="">请选择</option><option value="confirmed">我确认这项解释</option><option value="rejected">我不认同</option><option value="clarified">我想补充上下文</option><option value="needs_context">需要更多上下文</option></select></label><textarea aria-label="补充说明" maxlength="4000" placeholder="当时的语境、你的补充或不同解释……"></textarea><button class="button export-feedback">导出这条反馈</button><small>生成本地文件；由 Agent 导入后保存到长期档案。</small><p class="feedback-message" role="status"></p></div></div></details>')
        badges = ''.join(f'<span class="badge {esc(t)}">{LABELS[t]}候选</span>' for t in types)
        parts.append(f'<article class="archive" id="{esc(group["id"])}" data-types="{esc(" ".join(types))}"><header class="archive-head"><div><p class="eyebrow">ARCHIVE {index+1:02} / {esc(topic)}</p><h3>{esc(group["question"])}</h3></div><span class="archive-index">{index+1:02}</span></header><div class="archive-meta"><span>{date(notes[0]["effective_at"])} — {date(notes[-1]["effective_at"])}</span><span>{len(notes)} 条来源 · {len(books)} 本书</span>{badges}</div><div class="timeline">'+''.join(nodes)+'</div><div class="relations"><h4>为什么将它们放在一起？</h4>'+''.join(relations)+'</div></article>')
    def first_five(cards):
        if len(cards) <= 5:
            return ''.join(cards)
        return ''.join(cards[:5])+f'<details class="extra-archives"><summary>展开其他 {len(cards)-5} 个问题档案</summary>'+''.join(cards[5:])+'</details>'
    return groups, first_five(themes), first_five(parts), feedback


def semantic_cards(analysis):
    if not analysis or not analysis.get('result'):
        return '<p class="empty">尚无已验证的语义分析结果，下面保留规则参考。</p>'
    evidence = {r['evidence_id']:r for r in analysis['evidence']}
    cards = []
    for claim in analysis['result']['claims']:
        quotes = ''.join(quote_html(dict(evidence[q['evidence_id']], text=q['text'])) for q in claim['quotes'])
        counters = ''.join(quote_html(evidence[key]) for key in claim['counter_evidence_ids'])
        cards.append(f'<article class="semantic-card"><p class="eyebrow">{esc(SEMANTIC_LABELS[claim["category"]])} / 模型解释</p><h3>{esc(claim["statement"])}</h3><p>{esc(claim["rationale"])}</p><details><summary>查看原文、反向证据与局限</summary>{quotes}{counters}<p class="small">范围：{"本次样本" if claim["scope"]=="sample" else "所引片段"}。{esc("；".join(claim["limitations"]))}</p></details></article>')
    return ''.join(cards)


def render_journal(report, *, evidence=(), history=None, evolution=None, current_basis=None, contexts=None):
    """Render existing analyzed outputs; do not fetch data or invent semantic findings."""
    if history:
        validate_history(history)
    if evolution:
        validate_report(evolution)
        if history and history['dataset_id'] != evolution['history']['dataset_id']:
            raise ValueError('History dataset does not match the evolution report')
    if current_basis and not history:
        raise ValueError('A newer basis requires its dated history snapshot')
    if current_basis and current_basis['coverage'] != history['collection_coverage']:
        raise ValueError('Newer basis coverage does not match the dated history snapshot')
    basis = (current_basis or {}).get('basis', report['basis'])
    annual = (current_basis or {}).get('annual', report['annual'])
    coverage = (current_basis or {}).get('coverage', report['coverage'])
    basis_date = history['observed_at'] if current_basis else report['generatedAt']
    baseline_date = report['generatedAt']
    library = note_library(history, evidence)
    reviews = [n for n in library if n['kind']=='personal_review']
    underlines = [n for n in library if n['kind']=='underline']
    years = Counter(n['date'][:4] for n in reviews if n['date']!='日期未知')
    groups, theme_cards, archive_cards, feedback = timeline_groups(evolution, history, contexts or {})
    counts = Counter(t['relation'] for t in evolution['trajectories']) if evolution else Counter()
    semantic = report.get('llmAnalysis')
    semantic_scope = ''
    if semantic:
        c = semantic['coverage']
        semantic_scope = f'完整声明处理 {c["declared_complete_notes"]}/{c["selected_notes"]} 条选中笔记；可用正文 {c["available_notes"]} 条。'
    semantic_date = report.get('semanticGeneratedAt', baseline_date)
    complete_versions = set(evolution['coverage']['extraction']['complete_version_ids']) if evolution else set()
    selected = sum(n['kind']=='personal_review' and n['version_id'] in complete_versions for n in evolution['history']['notes']) if evolution else 0
    selected_reviews = len([n for n in evolution['history']['notes'] if n['kind']=='personal_review']) if evolution else 0
    evo_date = evolution['history']['observed_at'] if evolution else None
    nav = ''.join(f'<a href="#{key}" data-route="{key}"><span class="nav-number">{i:02}</span><span>{label}</span><span class="nav-arrow" aria-hidden="true">↗</span></a>' for i,(key,label,_) in enumerate(MODULES,1))
    available = lambda flag, key, suffix='': esc(str(basis[key])+suffix) if basis.get(flag) else '未取得'
    total_time = available('timeAvailable', 'totalReadTime')
    year_min = min((r['year'] for r in annual), default='—')
    year_max = max((r['year'] for r in annual), default='—')
    note_count = len(library)
    metric_html = f'<div class="metrics"><div class="metric"><span>累计阅读时长</span><b class="time-value">{total_time}</b></div><div class="metric"><span>有效阅读天数</span><b>{available("daysAvailable", "readDays")}<small>天</small></b></div><div class="metric"><span>官方读过 / 读完</span><b>{available("bookCountsAvailable", "booksRead")}<small>/ {available("bookCountsAvailable", "booksFinished")} 本</small></b></div><div class="metric"><span>已获取笔记正文</span><b>{note_count:,}<small>条</small></b></div></div>'
    scope_summary = f'观点档案实际分析 {selected} 条个人点评；笔记库收录 {len(reviews)} 条点评。' if evolution else '尚未导入观点演化结果。'
    scope_summary += '本次可见文本与已取得目录计数一致。' if coverage['notesComplete'] else '采集覆盖不完整，详见说明。'
    overview = f'''<section class="panel" id="overview" aria-labelledby="overview-title"><div class="hero"><div class="hero-copy"><p class="eyebrow">A PERSONAL READING JOURNAL / {year_min} — {year_max}</p><h1 id="overview-title">读过的书，<br>成为<em>思考的来路。</em></h1><p class="lead">从阅读的足迹，到留在书页里的声音。<br>在主题与时间之间，重新看见自己的理解。</p><a class="button hero-button" href="#thinking" data-route="thinking">走进我的思考 <span aria-hidden="true">↗</span></a><span class="hero-caption">阅读历史 · 跨书关联 · 观点演化</span></div><div class="folio"><div class="folio-top"><span>THE READING ATLAS</span><span>VOL. 01</span></div><div class="folio-glyph" aria-hidden="true">阅</div><div class="folio-orbit" aria-hidden="true"></div><div class="folio-bottom"><span>书页之间<br>理解慢慢发生</span><b>{year_min}<i>—</i>{year_max}</b></div></div></div>{source_line('官方统计与实际获取文本',basis_date)}{metric_html}<p class="overview-scope">{esc(scope_summary)}<a href="#coverage" data-route="coverage">覆盖说明 ↗</a></p><div class="section-title"><div><p class="eyebrow">WAYS INTO YOUR READING</p><h2>从记录，走向理解。</h2></div><span class="small">同一份报告，几种观察方式</span></div><div class="entry-grid"><a class="entry-card" href="#map" data-route="map"><span class="entry-number">01 / 阅读地图</span><h3>时间花在哪里？</h3><p>沿年度、分类与书籍，找到阅读的重心。</p><span class="entry-arrow" aria-hidden="true">↗</span></a><a class="entry-card" href="#notes" data-route="notes"><span class="entry-number">02 / 笔记与表达</span><h3>留下了什么？</h3><p>{len(reviews):,} 条个人点评，{len(underlines):,} 条原文划线。让结论回到原句。</p><span class="entry-arrow" aria-hidden="true">↗</span></a><a class="entry-card" href="#thinking" data-route="thinking"><span class="entry-number">03 / 我的思考</span><h3>理解如何形成？</h3><p>{len(groups)} 个问题档案。切换主题与时间，查看具体表达之间的联系。</p><span class="entry-arrow" aria-hidden="true">↗</span></a></div><div class="overview-end"><p class="serif">“不是每一次不同的表达，<br>都意味着观点的反转。”</p><div><p class="eyebrow">READ WITH CONTEXT</p><p>观点分析保留语境、时间和不确定性。当前有 {sum(counts.values())} 项关系候选；用户反馈与模型解释分别保存。</p><a class="text-button" href="#coverage" data-route="coverage">查看本次数据范围 ↗</a></div></div></section>'''
    chart_columns = ''.join(f'<div class="annual-col"><div class="annual-space"><span class="annual-bar" data-hours="{r["hours"]}" data-days="{r["readDays"]}" style="height:{max(1,r["hours"] / max((x["hours"] for x in annual),default=1)*100) if any(x["hours"] for x in annual) else 0:.2f}%"></span></div><b class="annual-value">{r["hours"]}</b><span>{r["year"]}</span><small>{r["readDays"]} 天</small></div>' for r in annual)
    categories = rank_list(report['categories'], 'hours', ' h') or '<p class="empty">未取得分类统计。</p>'
    longest = rank_list([dict(r,hours=round(r['seconds']/3600,1)) for r in report['readLongest']], 'hours', ' h')
    authors = ''.join(f'<div class="author-row"><span>{i+1:02}</span><b>{esc(name)}</b><small>加权线索 {score}</small></div>' for i,(name,score) in enumerate(report['people']))
    completion = round(basis['booksFinished']/basis['booksRead']*100,1) if basis.get('bookCountsAvailable') and basis['booksRead'] and 0 <= basis['booksFinished'] <= basis['booksRead'] else None
    summary_status = coverage['groups'].get('汇总与目录', {})
    shelf_available = (summary_status.get('expected', 0) > 0
                       and not any(summary_status.get(k, 0) for k in ('failed', 'not_requested', 'unknown'))
                       and summary_status.get('success', 0) + summary_status.get('empty', 0) == summary_status['expected'])
    shelf_total = basis['shelfTotal'] if shelf_available else '未确认'
    shelf_books, shelf_albums, shelf_mp = (basis['shelfBooks'], basis['albums'], basis['mpCount']) if shelf_available else ('—', '—', '—')
    reading_map = f'<section class="panel" id="map">{heading(2,"阅读地图","阅读的重心，藏在日积月累的时间里。")}{source_line("年度统计",basis_date)}<article class="paper-card annual-card"><div class="card-heading"><div><p class="eyebrow">READING OVER THE YEARS</p><h2>每一年，都有自己的节奏。</h2></div><div class="segmented" role="group" aria-label="年度统计口径"><button class="active" data-chart="hours" aria-pressed="true">阅读时长</button><button data-chart="days" aria-pressed="false">阅读天数</button></div></div><div class="annual-chart" role="img" aria-label="年度阅读时长与阅读天数">{chart_columns}</div><p class="small" id="chart-caption">单位：小时。{year_max} 年截至快照日期，不与完整年度直接等量比较。</p></article>{source_line("分类、书籍与作者线索",baseline_date)}<div class="two-col"><article class="paper-card"><p class="eyebrow">BY SUBJECT</p><h2>阅读分类</h2>{categories}<p class="small">分类来自接口；占比的分母为返回的分类时长。</p></article><article class="paper-card"><p class="eyebrow">TIME WITH BOOKS</p><h2>相处较久的书</h2>{longest or "<p class=empty>未取得书籍时长。</p>"}</article></div><div class="two-col lower-grid"><article class="paper-card"><p class="eyebrow">AUTHOR TRACES</p><h2>作者线索</h2>{authors or "<p class=empty>未取得作者线索。</p>"}<p class="small">综合作者偏好与笔记目录的加权结果，不是精确阅读次数，也不代表思想影响。</p></article><article class="paper-card shelf-card"><p class="eyebrow">THE SHELF</p><h2>书架与读完情况</h2><div class="shelf-number">{shelf_total}<span>个书架条目</span></div><div class="shelf-breakdown"><span>电子书 <b>{shelf_books}</b></span><span>听书专辑 <b>{shelf_albums}</b></span><span>公众号聚合 <b>{shelf_mp}</b></span></div><p class="completion">官方读完比例 <b>{completion if completion is not None else "未取得"}{"%" if completion is not None else ""}</b></p><p class="small">只描述官方“读完 / 读过”比例，不用于判断自律或理解程度。书架统计快照 {date(basis_date)}。</p></article></div></section>'
    top_books = rank_list(report['topNoteBooks'], 'notes', ' 条')
    note_years = rank_list([dict(name=year,count=count) for year,count in sorted(years.items())], 'count', ' 条')
    library_years = {n['date'][:4] for n in library if n['date']!='日期未知'}
    year_options = ''.join(f'<option value="{esc(y)}">{esc(y)} 年</option>' for y in sorted(library_years, reverse=True))
    notes_panel = f'<section class="panel" id="notes">{heading(3,"笔记与表达","划线是你停留的地方，点评是你留下的声音。")}{source_line("可见笔记正文",history["observed_at"] if history else baseline_date)}<div class="note-stats"><div><b>{len(reviews):,}</b><span>个人点评</span></div><div><b>{len(underlines):,}</b><span>原文划线</span></div><p>划线保留书中的声音。<br>个人立场需要由你的点评支持。</p></div><div class="two-col"><details class="paper-card note-distribution"><summary>哪些书留下了更多笔记？</summary>{source_line("目录笔记数，含点评、划线及书签",baseline_date)}{top_books}</details><details class="paper-card note-distribution"><summary>点评的年份分布</summary>{note_years}<p class="small">按可用源时间计数，不等于年度阅读量。缺少日期的记录不进入年份分布。</p></details></div><div class="section-title"><div><p class="eyebrow">THE SOURCE LIBRARY</p><h2>原句，随时可以回看。</h2></div></div><div class="library-tools"><div class="segmented" role="group" aria-label="笔记类型"><button class="active" data-note-kind="all" aria-pressed="true">全部笔记</button><button data-note-kind="personal_review" aria-pressed="false">个人点评</button><button data-note-kind="underline" aria-pressed="false">原文划线</button></div><label class="search-wrap"><span class="sr-only">搜索笔记</span><input id="note-search" type="search" placeholder="搜索书名、作者或原句"></label><label><span class="sr-only">笔记年份</span><select id="note-year"><option value="all">所有年份</option>{year_options}<option value="unknown">日期未知</option></select></label></div><p class="small" id="note-count" role="status"></p><div id="note-list" class="note-list"></div><noscript><p>启用 JavaScript 后可以本地检索笔记。完整报告内容和观点证据仍可阅读。</p></noscript><div class="pagination"><button class="text-button" id="note-prev">← 上一页</button><span id="note-page" class="small"></span><button class="text-button" id="note-next">下一页 →</button></div></section>'
    filters = '<button class="active" data-relation="all" aria-pressed="true">全部</button>'+''.join(f'<button data-relation="{key}" aria-pressed="false">{LABELS[key]} <span>{count}</span></button>' for key,count in counts.items())
    rule_themes = ''.join(f'<details class="rule-row"><summary>{esc(t["name"])}<span>{t["personalMatchedItems"]} 条点评 · {t["personalBookCount"]} 本书</span></summary><p class="small">{esc(t["source"])}。规则预设的问题提示：{esc(t["question"])}</p>'+''.join(quote_html(q) for q in t['evidence'])+'</details>' for t in report['themes'])
    styles = ''.join(f'<div class="signal-row"><b>{esc(s["name"])}</b><span>{s["reviewHits"]} 次点评关键词命中 · {s["bookCount"]} 本来源书</span></div>' for s in report['styles'] if s['personalSufficient'])
    values = ''.join(f'<details class="rule-row"><summary>{esc(v["name"])}</summary>'+''.join(quote_html(q) for q in v['evidence'])+'</details>' for v in report['values'])
    no_archives = '<p class="empty">尚无足够的观点比较结果。不能据此认定观点没有变化。</p>'
    thinking = f'<section class="panel" id="thinking">{heading(4,"我的思考","同一个问题，可以横向连接书籍，也可以纵向追溯时间。")}<div class="thinking-bar"><div class="segmented view-toggle" role="tablist" aria-label="我的思考视图"><button id="theme-tab" class="active" role="tab" aria-controls="theme-view" aria-selected="true" tabindex="0" data-thinking-view="theme">主题视图</button><button id="time-tab" role="tab" aria-controls="time-view" aria-selected="false" tabindex="-1" data-thinking-view="time">时间视图</button></div><span class="small">{len(groups)} 个问题档案 · {sum(counts.values())} 项关系候选</span></div><div id="theme-view" role="tabpanel" aria-labelledby="theme-tab"><div class="scope-strip"><span>问题档案</span><p>来自时间分析的选中材料，切换视角不代表新增全量分析。完整声明处理 {selected}/{selected_reviews} 条选中个人点评；快照 {date(evo_date)}。</p></div><div class="question-grid">{theme_cards or no_archives}</div><div class="section-title"><div><p class="eyebrow">WIDER READING INSIGHTS</p><h2>更广范围的语义观察</h2></div></div>{source_line("已有大模型分析",semantic_date)}<p class="small">{esc(semantic_scope)}解释来自原报告，未因页面整合重新分析。</p><div class="semantic-grid">{semantic_cards(semantic)}</div><details class="reference-block"><summary>规则参考：主题、表达与关注倾向</summary>{source_line("规则分析",baseline_date)}<p class="small">关键词线索与模型解释分开呈现。强度不是能力评分，不确认价值认同或焦虑来源。</p>{rule_themes}<h3>表达方式线索</h3>{styles or "<p class=small>证据不足，不作表达倾向结论。</p>"}<h3>点评中的关注词汇</h3>{values}</details></div><div id="time-view" role="tabpanel" aria-labelledby="time-tab"><div class="scope-strip"><span>时间证据</span><p>分析了 {selected} 条选中点评，来源创建／修改时间见各节点。首次采集前的旧版本未知；解释仍是候选。快照 {date(evo_date)}。</p></div><div class="timeline-tools"><div class="relation-filters" role="group" aria-label="关系类型">{filters}</div><label class="search-wrap"><span class="sr-only">搜索观点档案</span><input id="archive-search" type="search" placeholder="搜索问题、书名或原句"></label></div><p class="small" id="archive-count" role="status"></p>{archive_cards or no_archives}<p id="archive-empty" class="empty" hidden>没有匹配的档案。请调整搜索或关系类型。</p></div></section>'
    suggestion_cards = ''.join(f'<article class="paper-card"><p class="eyebrow">PRACTICE / {i+1:02}</p><h3>{esc(title)}</h3><ul>'+''.join(f'<li>{esc(item)}</li>' for item in items)+'</ul></article>' for i,(title,items) in enumerate(report['suggestions'].items()))
    recommendations = ''.join(f'<article class="book-card"><span class="book-index">{i+1:02}</span><div><p class="eyebrow">{esc(b["lane"])}</p><h3>{esc(b["title"])}</h3><p class="small">{esc(b["author"])}</p><p>{esc(b["why"])}</p></div></article>' for i,b in enumerate(report['recommendedBooks']))
    concentration = report['informationCocoon']
    reminders = list(concentration['signals'])+list(report['strictProfile'])+list(report['blindSpots'])
    inspiration = f'<section class="panel" id="inspiration">{heading(5,"阅读启发","把发现变成一个可继续追问的问题。")}{source_line("基于原报告的可选建议",baseline_date)}<div class="inspiration-intro"><p class="serif">下一本书，<br>不必只是下一本。</p><p>可以带着一个问题重读，可以找一段不同的解释，也可以先写下自己的条件和反例。建议是可选练习，不是对能力或人格的诊断。</p></div><div class="two-col">{suggestion_cards}</div><details class="reference-block"><summary>阅读集中度与覆盖提醒</summary><p>{esc(concentration["summary"])}</p><ul>'+''.join(f'<li>{esc(s)}</li>' for s in reminders)+f'</ul><p class="small">分类集中度和官方完成比例是可观察指标，不能证明信息茧房、行动力或知识质量。</p></details><div class="section-title"><div><p class="eyebrow">POSSIBLE NEXT READS</p><h2>为问题找一些新的入口。</h2></div></div><p class="small">以下保留原报告的规则推荐，来自预设书单；并非本次模型重新选书或实时书籍检索。</p><div class="book-grid">{recommendations}</div></section>'
    coverage_rows = [('基础统计快照',date(basis_date)),('规则／分类／广范围语义快照',date(baseline_date)),('观点档案快照',date(evo_date)),('当前笔记库',f'{note_count} 条正文；{len(reviews)} 条个人点评，{len(underlines)} 条划线'),('观点分析',f'{selected} 条选中点评；不等于全账户语义分析')]
    lines = coverage_lines(coverage)
    if semantic:
        lines += ['较广范围语义分析：'+semantic_scope] + list(semantic['result']['abstentions'] if semantic.get('result') else ['语义结果未完成。'])
    if evolution:
        lines += coverage_text(evolution) + list(evolution['abstentions'])
    coverage_panel = f'<section class="panel" id="coverage">{heading(0,"数据与证据范围","让每个结论，都能找到它实际使用的材料。")}<div class="paper-card"><table class="coverage-table">'+''.join(f'<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>' for k,v in coverage_rows)+'</table><div class="coverage-lines">'+''.join(f'<p>{esc(s)}</p>' for s in lines)+'</div></div><p class="small">此页面在本地检索与导出反馈，无外部资源请求。引用与结构校验不等于语义准确率认证。</p></section>'
    payload = dict(notes=library, feedback=feedback, annual=annual)
    css = (ASSETS/'journal.css').read_text(encoding='utf-8')
    js = (ASSETS/'journal.js').read_text(encoding='utf-8')
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta name="referrer" content="no-referrer"><title>我的阅读手记 · {esc(report['title'])}</title><style>{css}</style></head><body><a class="skip-link" href="#main">跳到主要内容</a><div class="shell"><aside class="sidebar"><a class="brand" href="#overview" data-route="overview"><span class="brand-mark" aria-hidden="true">阅</span><span>阅读手记<small>THE READING JOURNAL</small></span></a><p class="side-label">目录 / CONTENTS</p><nav aria-label="报告模块">{nav}</nav><div class="side-end"><a class="coverage-link" href="#coverage" data-route="coverage">数据与证据范围 <span aria-hidden="true">↗</span></a><span class="private"><i></i>私人 · 本地阅读</span><p>保留原句<br>也保留解释的不确定</p></div></aside><main id="main" tabindex="-1"><div class="topbar"><span>微信读书 <i>/</i> <span id="current-module">阅读总览</span></span><div class="topbar-tools"><a href="#coverage" data-route="coverage">数据范围 ↗</a><span class="edition">PERSONAL EDITION <b>01</b></span></div></div>{overview}{reading_map}{notes_panel}{thinking}{inspiration}{coverage_panel}<footer class="footer"><span>读过的书，成为思考的来路。</span><span>本地阅读报告 · 数据范围见各模块</span></footer></main></div><script id="journal-data" type="application/json">{json_script(payload)}</script><script>{js}</script></body></html>'''
