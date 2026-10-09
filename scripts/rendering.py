"""Offline Markdown/HTML rendering of evidence-scoped reports."""
from __future__ import annotations
import html
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
if __package__:
    from .common import as_list, clean_text, truncate, seconds_text
    from .coverage import coverage_lines
    from .enhanced_rendering import semantic_markdown, semantic_html
else:
    from common import as_list, clean_text, truncate, seconds_text
    from coverage import coverage_lines
    from enhanced_rendering import semantic_markdown, semantic_html

def pct_bar(value: float, max_value: float) -> int:
    if value is None or max_value <= 0:
        return 0
    return max(4, min(100, round(value / max_value * 100)))


def score_label(score: Optional[int]) -> str:
    return "暂不评分（证据不足）" if score is None else f"{score}/100"


CHART_COLORS = ["#0f766e", "#d65f42", "#4f46e5", "#d97706", "#2563eb", "#7c3aed", "#64748b"]


def fmt_number(value: Any, suffix: str = "") -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return f"0{suffix}"
    if number.is_integer():
        return f"{int(number)}{suffix}"
    return f"{number:.1f}{suffix}"


def render_donut_chart(title: str, segments: List[Dict[str, Any]], center: str, note: str = "") -> str:
    cleaned = []
    for idx, item in enumerate(segments):
        try:
            value = float(item.get("value") or 0)
        except (TypeError, ValueError):
            value = 0
        if value <= 0:
            continue
        cleaned.append({
            "label": clean_text(item.get("label")),
            "value": value,
            "display": clean_text(item.get("display")) or fmt_number(value),
            "color": item.get("color") or CHART_COLORS[idx % len(CHART_COLORS)],
        })
    if not cleaned:
        return ""

    total = sum(item["value"] for item in cleaned)
    cursor = 0.0
    slices = []
    for item in cleaned:
        start = cursor
        cursor += item["value"] / total * 100
        slices.append(f'{item["color"]} {start:.2f}% {cursor:.2f}%')
    legend = []
    for item in cleaned:
        legend.append(
            '<li>'
            f'<i style="background:{html.escape(item["color"])}"></i>'
            f'<span>{html.escape(item["label"])}</span>'
            f'<strong>{html.escape(item["display"])}</strong>'
            '</li>'
        )
    note_html = f'<p class="chart-note">{html.escape(note)}</p>' if note else ""
    return (
        '<article class="donut-card">'
        f'<div class="donut" style="background:conic-gradient({", ".join(slices)})"><span>{html.escape(center)}</span></div>'
        '<div class="donut-copy">'
        f'<h3>{html.escape(title)}</h3>{note_html}'
        f'<ul class="legend">{"".join(legend)}</ul>'
        '</div>'
        '</article>'
    )


def render_markdown(report: Dict[str, Any]) -> str:
    b = report["basis"]
    lines: List[str] = []
    lines.append(f"# {report['title']}")
    lines.append("")
    lines.append(f"生成时间：{report['generatedAt']}")
    lines.append("")
    summary = report["profileSummary"]
    if report.get("llmAnalysis"):
        summary = {"label": "大模型增强阅读报告", "tagline": "语义结论、原始证据与本地统计分别呈现；分析范围见数据覆盖说明。"}
    lines.append(f"**画像摘要：{summary['label']}**")
    lines.append("")
    lines.append(summary["tagline"])
    lines.append("")
    lines.append("## 数据基础")
    lines.append("")
    limited = "；本次为抽样导出" if b["limited"] else ""
    lines.append(
        f"本报告基于本次可见数据：累计阅读 {b['totalReadTime']}，有效阅读 {b['readDays'] if b['daysAvailable'] else '未获取'} 天，"
        f"读过 {b['booksRead'] if b['bookCountsAvailable'] else '未获取'} 本，读完 {b['booksFinished'] if b['bookCountsAvailable'] else '未获取'} 本，官方笔记口径 {b['notes'] if b['notesAvailable'] else '未获取'} 条。"
        f"书架可见 {b['shelfTotal']} 个条目，其中电子书 {b['shelfBooks']} 本、有声/专辑 {b['albums']} 个、文章收藏入口 {b['mpCount']} 个。"
    )
    if not b["officialStatsAvailable"]:
        lines[-1] = "累计时长、阅读天数和官方读过/读完计数未获取，不能视为零；以下为本次取得的目录和有效文本计数。"
    lines.append(
        f"本次取得的笔记目录包含 {b['notebookBooks']} 本书，尝试获取 {b['exportedBooks']} 本明细，"
        f"包含 {b['exportedUnderlines']} 条划线和 {b['exportedReviews']} 条个人想法/点评；"
        f"另导出 {b['progressRows']} 条阅读进度和 {b['bookInfoRows']} 条书籍详情{limited}。"
    )
    lines.append("")

    lines.extend(["### 数据覆盖情况", ""])
    lines.extend(f"- {line}" for line in coverage_lines(report["coverage"]))
    lines.append("")
    lines.append("## 阅读地图")
    if report.get("llmAnalysis"):
        lines[-1:] = [semantic_markdown(report['llmAnalysis']), "## 阅读地图"]
    lines.append("")
    if report["annual"]:
        lines.append("### 年度阅读")
        for y in report["annual"]:
            if y["seconds"] > 0 or y["readDays"] > 0:
                lines.append(f"- {y['year']}：{seconds_text(y['seconds'])}，{y['readDays']} 天")
        lines.append("")
    if report["categories"]:
        lines.append("### 分类偏好")
        for c in report["categories"]:
            lines.append(f"- {c['name']}：{c['hours']} 小时，{c['books']} 本")
        lines.append("")
    if report["readLongest"]:
        lines.append("### 阅读时长 Top")
        for r in report["readLongest"][:8]:
            author = f"（{r['author']}）" if r["author"] else ""
            lines.append(f"- {r['title']}{author}：{r['time']}")
        lines.append("")
    if report["topNoteBooks"]:
        lines.append("### 笔记最多的书")
        for r in report["topNoteBooks"][:10]:
            author = f"（{r['author']}）" if r["author"] else ""
            lines.append(f"- {r['title']}{author}：{r['notes']} 条，其中想法 {r['reviews']}、划线 {r['underlines']}")
        lines.append("")

    lines.append("## 主题与问题意识")
    lines.append("")
    for theme in report["themes"]:
        lines.append(f"### {theme['name']}")
        lines.append(f"核心问题：{theme['question']}")
        lines.append(theme["source"])
        for ev in theme["evidence"]:
            lines.append("")
            lines.append(f"> {ev['text']}")
            lines.append(f"> 来源：{ev['title']}，{ev['kind']}")
        lines.append("")
    if report["questions"]:
        lines.append("反复出现的问题可以概括为：")
        for q in report["questions"]:
            lines.append(f"- {q}")
        lines.append("")

    lines.append("## 思考方式")
    lines.append("")
    for style in report["styles"]:
        lines.append(f"- {style['name']}：{style['level']}，信号强度 {style['score']}")
        for ev in style["evidence"]:
            lines.append(f"  - 例证：{ev['text']}（{ev['title']}）")
    lines.append("")

    lines.append("## 价值观、焦虑与长期方向")
    lines.append("")
    lines.append("以下仅为个人点评中的词汇关注信号，不确认价值认同、焦虑来源或长期方向。")
    for value in report["values"]:
        lines.append(f"- {value['name']}：相关信号强度 {value['score']}")
        for ev in value["evidence"]:
            lines.append(f"  - 例证：{ev['text']}（{ev['title']}）")
    lines.append("")

    if report["people"]:
        lines.append("## 常出现的人物/作者线索")
        lines.append("")
        lines.append("这些名字来自偏好作者、书籍作者和笔记文本中的显性提及，只代表阅读关注度，不等同于价值认同。")
        for name, count in report["people"][:10]:
            lines.append(f"- {name}：{count}")
        lines.append("")

    lines.append("## 读者画像")
    lines.append("")
    for p in report["portrait"]:
        lines.append(p)
        lines.append("")

    cocoon = report["informationCocoon"]
    lines.append("## 信息茧房")
    lines.append("")
    lines.append(f"集中信号：{cocoon['level']}，{score_label(cocoon['score'])}。")
    lines.append("")
    lines.append(cocoon["summary"])
    lines.append("")
    lines.append("### 证据")
    for item in cocoon["signals"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### 破茧动作")
    for item in cocoon["antidotes"]:
        lines.append(f"- {item}")
    lines.append("")

    if report["recommendedBooks"]:
        lines.append("## 推荐书单")
        lines.append("")
        for book in report["recommendedBooks"]:
            lines.append(f"- 《{book['title']}》{book['author']}｜{book['lane']}：{book['why']}")
        lines.append("")

    lines.append("## 温馨提示：下面可能有一点刺耳")
    lines.append("")
    lines.append(report["strictNotice"])
    lines.append("")
    lines.append("### 严格诊断")
    for item in report["strictProfile"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### 可能的盲区")
    for item in report["blindSpots"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### 维度打分")
    for item in report["dimensionScores"]:
        lines.append(f"- {item['name']}：{score_label(item['score'])}。{item['note']}")
    lines.append("")

    lines.append("## 建议")
    lines.append("")
    for title, items in report["suggestions"].items():
        lines.append(f"### {title}")
        for item in items:
            lines.append(f"- {item}")
        lines.append("")
    lines.append("## 更严格的执行建议")
    lines.append("")
    for title, items in report["sharperAdvice"].items():
        lines.append(f"### {title}")
        for item in items:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def metric(label: str, value: Any, icon: str = "") -> str:
    icon_html = f'<span class="metric-icon">{html.escape(icon)}</span>' if icon else ""
    return (
        '<div class="metric">'
        f'{icon_html}<strong>{html.escape(str(value))}</strong><span>{html.escape(label)}</span>'
        '</div>'
    )


def render_bar(label: str, value: float, max_value: float, suffix: str = "") -> str:
    width = pct_bar(value, max_value)
    return (
        '<div class="bar">'
        f'<div>{html.escape(label)}</div>'
        f'<div class="track"><div class="fill" style="width:{width}%"></div></div>'
        f'<div>{html.escape(str(value))}{html.escape(suffix)}</div>'
        '</div>'
    )


def quote_html(ev: Dict[str, str]) -> str:
    return (
        '<div class="quote">'
        f'{html.escape(ev["text"])}'
        f'<small>{html.escape(ev["title"])} · {html.escape(ev["kind"])}</small>'
        '</div>'
    )


def svg_icon(paths: str) -> str:
    return (
        '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'{paths}</svg>'
    )


def section_icon(title: str) -> str:
    icons = [
        ("数据", '<rect x="3" y="3" width="18" height="18" rx="3"></rect><path d="M7 15l3-3 3 2 4-6"></path>', "#dcfce7", "#15803d"),
        ("地图", '<path d="M9 18l-6 3V6l6-3 6 3 6-3v15l-6 3-6-3z"></path><path d="M9 3v15"></path><path d="M15 6v15"></path>', "#dbeafe", "#2563eb"),
        ("主题", '<circle cx="12" cy="12" r="9"></circle><path d="M9.5 9a2.6 2.6 0 0 1 5 1.2c0 1.8-2.5 2-2.5 3.8"></path><path d="M12 17h.01"></path>', "#fef3c7", "#d97706"),
        ("思考", '<circle cx="7" cy="8" r="2"></circle><circle cx="17" cy="8" r="2"></circle><circle cx="12" cy="17" r="2"></circle><path d="M9 9.5l2 5"></path><path d="M15 9.5l-2 5"></path><path d="M9 8h6"></path>', "#ede9fe", "#7c3aed"),
        ("价值", '<path d="M12 3v18"></path><path d="M5 7h14"></path><path d="M6 7l-3 7h6l-3-7z"></path><path d="M18 7l-3 7h6l-3-7z"></path>', "#fee2e2", "#dc2626"),
        ("人物", '<circle cx="12" cy="8" r="4"></circle><path d="M4 21a8 8 0 0 1 16 0"></path>', "#cffafe", "#0891b2"),
        ("画像", '<path d="M4 7V5a2 2 0 0 1 2-2h2"></path><path d="M16 3h2a2 2 0 0 1 2 2v2"></path><path d="M20 17v2a2 2 0 0 1-2 2h-2"></path><path d="M8 21H6a2 2 0 0 1-2-2v-2"></path><circle cx="12" cy="10" r="3"></circle><path d="M7 17a5 5 0 0 1 10 0"></path>', "#e0e7ff", "#4f46e5"),
        ("信息茧房", '<circle cx="12" cy="12" r="8"></circle><circle cx="12" cy="12" r="4"></circle><path d="M4 12h16"></path><path d="M12 4v16"></path>', "#f3e8ff", "#9333ea"),
        ("推荐书单", '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path><path d="M9 7h7"></path><path d="M9 11h6"></path>', "#ffedd5", "#ea580c"),
        ("温馨", '<path d="M10.3 4.3l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-2.7l-8-14a2 2 0 0 0-3.4 0z"></path><path d="M12 9v4"></path><path d="M12 17h.01"></path>', "#ffe4e6", "#e11d48"),
        ("建议", '<path d="M12 2l3 7h7l-5.6 4.2L18.5 21 12 16.7 5.5 21l2.1-7.8L2 9h7l3-7z"></path>', "#ccfbf1", "#0f766e"),
    ]
    for key, paths, bg, color in icons:
        if key in title:
            return (
                f'<span class="section-icon" style="--icon-bg:{bg};--icon-color:{color}">'
                f'{svg_icon(paths)}</span>'
            )
    fallback_paths = '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>'
    return (
        '<span class="section-icon" style="--icon-bg:#e2e8f0;--icon-color:#475569">'
        f'{svg_icon(fallback_paths)}</span>'
    )


def section(title: str, body: str, section_id: str = "", extra_class: str = "") -> str:
    attrs = []
    if section_id:
        attrs.append(f'id="{html.escape(section_id)}"')
    cls = extra_class.strip()
    if cls:
        attrs.append(f'class="{html.escape(cls)}"')
    attr_text = " " + " ".join(attrs) if attrs else ""
    return (
        f"<section{attr_text}>"
        f'<div class="section-heading">{section_icon(title)}'
        f"<h2>{html.escape(title)}</h2></div>{body}</section>"
    )


def render_profile_visual(report: Dict[str, Any]) -> str:
    summary = report["profileSummary"]
    parts = [
        '<div class="portrait-shell">',
        '<div class="portrait-lead">',
        f'<div class="profile-label">{html.escape(summary["label"])}</div>',
        f'<p>{html.escape(summary["tagline"])}</p>',
        '<div class="profile-keywords">',
    ]
    for keyword in summary.get("keywords", [])[:5]:
        parts.append(f'<span>{html.escape(keyword)}</span>')
    parts.extend(['</div>', '</div>', '<div class="score-board">'])
    for item in report["dimensionScores"]:
        width = pct_bar(item["score"], 100)
        parts.append(
            '<div class="score-tile">'
            f'<div class="score-head"><strong>{html.escape(item["name"])}</strong><span>{score_label(item["score"])}</span></div>'
            f'<div class="mini-track"><div style="width:{width}%"></div></div>'
            f'<p>{html.escape(item["note"])}</p>'
            '</div>'
        )
    parts.extend(['</div>', '</div>'])

    if report["styles"] or report["themes"]:
        parts.append('<div class="portrait-viz-grid">')
        if report["styles"]:
            parts.append('<div class="viz-panel"><h3>思考方式雷达</h3>')
            max_style = max((s["score"] for s in report["styles"]), default=1)
            for style in report["styles"][:5]:
                parts.append(render_bar(style["name"], style["score"], max_style))
            parts.append('</div>')
        if report["themes"]:
            parts.append('<div class="viz-panel"><h3>主题星图</h3><div class="bubble-cloud">')
            max_theme = max((t["score"] for t in report["themes"]), default=1)
            for theme in report["themes"][:8]:
                size = 12 + pct_bar(theme["score"], max_theme) // 8
                parts.append(
                    f'<span style="font-size:{size}px">{html.escape(theme["name"])}</span>'
                )
            parts.append('</div></div>')
        parts.append('</div>')
    return "\n".join(parts)


def render_information_cocoon(cocoon: Dict[str, Any]) -> str:
    width = pct_bar(cocoon["score"], 100)
    parts = [
        '<div class="cocoon-panel">',
        '<div>',
        f'<div class="risk-label">集中信号：{html.escape(cocoon["level"])}</div>',
        f'<p>{html.escape(cocoon["summary"])}</p>',
        '</div>',
        '<div class="risk-meter">',
        f'<strong>{score_label(cocoon["score"])}</strong>',
        f'<div class="mini-track"><div style="width:{width}%"></div></div>',
        '</div>',
        '</div>',
        '<div class="two-col">',
        '<div class="mini-card compact"><h3>证据</h3><ul>',
    ]
    for item in cocoon["signals"]:
        parts.append(f'<li>{html.escape(item)}</li>')
    parts.append('</ul></div><div class="mini-card compact"><h3>破茧动作</h3><ul>')
    for item in cocoon["antidotes"]:
        parts.append(f'<li>{html.escape(item)}</li>')
    parts.append('</ul></div></div>')
    return "\n".join(parts)


def render_book_cards(books: List[Dict[str, str]]) -> str:
    if not books:
        return '<p class="muted">当前证据不足，暂不生成推荐书单。</p>'
    parts = ['<div class="book-grid">']
    for book in books:
        parts.append(
            '<article class="book-card">'
            f'<span>{html.escape(book["lane"])}</span>'
            f'<h3>《{html.escape(book["title"])}》</h3>'
            f'<small>{html.escape(book["author"])}</small>'
            f'<p>{html.escape(book["why"])}</p>'
            '</article>'
        )
    parts.append('</div>')
    return "\n".join(parts)


def top_segments(rows: List[Dict[str, Any]], label_key: str, value_key: str, suffix: str = "", limit: int = 6) -> List[Dict[str, Any]]:
    sorted_rows = sorted(rows, key=lambda x: float(x.get(value_key) or 0), reverse=True)
    segments: List[Dict[str, Any]] = []
    shown_total = 0.0
    total = sum(float(row.get(value_key) or 0) for row in sorted_rows)
    for idx, row in enumerate(sorted_rows[:limit]):
        value = float(row.get(value_key) or 0)
        if value <= 0:
            continue
        shown_total += value
        segments.append({
            "label": clean_text(row.get(label_key)),
            "value": value,
            "display": fmt_number(value, suffix),
            "color": CHART_COLORS[idx % len(CHART_COLORS)],
        })
    other = total - shown_total
    if other > 0:
        segments.append({
            "label": "其他",
            "value": other,
            "display": fmt_number(other, suffix),
            "color": CHART_COLORS[-1],
        })
    return segments


def render_basis_charts(basis: Dict[str, Any]) -> str:
    if not basis["bookCountsAvailable"]:
        return ""
    read_count = int(basis.get("booksRead") or 0)
    finished = int(basis.get("booksFinished") or 0)
    unfinished = max(read_count - finished, 0)
    completion = round(finished / read_count * 100) if read_count else 0
    total_notes = int(basis.get("exportedUnderlines") or 0) + int(basis.get("exportedReviews") or 0)
    idea_ratio = round(int(basis.get("exportedReviews") or 0) / total_notes * 100) if total_notes else 0

    charts = [
        render_donut_chart(
            "完读结构",
            [
                {"label": "已读完", "value": finished, "display": f"{finished} 本", "color": "#0f766e"},
                {"label": "待读完/未完读", "value": unfinished, "display": f"{unfinished} 本", "color": "#d65f42"},
            ],
            f"{completion}%",
            "衡量阅读闭环，不评价阅读质量。",
        ),
        render_donut_chart(
            "笔记构成",
            [
                {"label": "划线", "value": basis.get("exportedUnderlines"), "display": f"{basis.get('exportedUnderlines', 0)} 条", "color": "#4f46e5"},
                {"label": "个人想法", "value": basis.get("exportedReviews"), "display": f"{basis.get('exportedReviews', 0)} 条", "color": "#d97706"},
            ],
            f"{idea_ratio}%",
            "中心值为个人想法占比。",
        ),
        render_donut_chart(
            "书架构成",
            [
                {"label": "电子书", "value": basis.get("shelfBooks"), "display": f"{basis.get('shelfBooks', 0)} 本", "color": "#2563eb"},
                {"label": "有声/专辑", "value": basis.get("albums"), "display": f"{basis.get('albums', 0)} 个", "color": "#7c3aed"},
                {"label": "文章入口", "value": basis.get("mpCount"), "display": f"{basis.get('mpCount', 0)} 个", "color": "#64748b"},
            ],
            "书架",
            "展示可见条目的类型分布。",
        ),
    ]
    charts = [chart for chart in charts if chart]
    if not charts:
        return ""
    return '<div class="chart-row">' + "\n".join(charts) + '</div>'


def render_map_charts(report: Dict[str, Any]) -> str:
    charts = []
    if report["categories"]:
        top_category = report["categories"][0]["name"]
        charts.append(render_donut_chart(
            "分类阅读占比",
            top_segments(report["categories"], "name", "hours", "h", limit=6),
            "分类",
            f"最高分类：{top_category}。",
        ))
    annual_positive = [row for row in report["annual"] if float(row.get("hours") or 0) > 0]
    if annual_positive:
        top_year = max(annual_positive, key=lambda x: float(x.get("hours") or 0))["year"]
        charts.append(render_donut_chart(
            "年度阅读占比",
            top_segments(annual_positive, "year", "hours", "h", limit=6),
            str(top_year),
            "中心值为阅读时长最高的年份。",
        ))
    note_rows = [
        {"title": row["title"], "notes": row["notes"]}
        for row in report["topNoteBooks"][:8]
        if int(row.get("notes") or 0) > 0
    ]
    if note_rows:
        charts.append(render_donut_chart(
            "高笔记书籍分布",
            top_segments(note_rows, "title", "notes", " 条", limit=5),
            "笔记",
            "展示笔记最集中的几本书。",
        ))
    charts = [chart for chart in charts if chart]
    if not charts:
        return ""
    return '<div class="chart-row map-charts">' + "\n".join(charts) + '</div>'


def render_theme_overview(themes: List[Dict[str, Any]]) -> str:
    if not themes:
        return '<p class="muted">当前主题证据不足，暂不生成主题概览。</p>'
    top = themes[:6]
    chart = render_donut_chart(
        "主题信号分布",
        [
            {
                "label": theme["name"],
                "value": theme["score"],
                "display": f'信号 {theme["score"]}',
                "color": CHART_COLORS[idx % len(CHART_COLORS)],
            }
            for idx, theme in enumerate(top)
        ],
        "主题",
        "用于概览本节展开的主要问题，不代表价值排序。",
    )
    parts = [
        '<div class="section-overview">',
        '<div class="overview-copy">',
        '<h3>本节会展开这些问题</h3>',
        f'<p>核心主题集中在 {html.escape("、".join(t["name"] for t in top[:4]))} 等方向。下面每个主题都会给出核心问题和代表性笔记证据。</p>',
        '</div>',
        chart,
    ]
    parts.append('</div>')
    return "\n".join(parts)


def render_thinking_overview(styles: List[Dict[str, Any]]) -> str:
    if not styles:
        return '<p class="muted">当前思考方式证据不足，暂不生成思考方式概览。</p>'
    top = styles[:6]
    max_score = max((s["score"] for s in top), default=1)
    parts = [
        '<div class="thinking-overview">',
        '<div class="overview-copy">',
        '<h3>思考方式概览</h3>',
        f'<p>当前最突出的处理文本方式是 {html.escape("、".join(s["name"] for s in top[:3]))}。下面的可视化只展示信号强弱，详细例证放在后文。</p>',
        '</div>',
        '<div class="style-meter-grid">',
    ]
    for idx, style in enumerate(top):
        width = pct_bar(style["score"], max_score)
        color = CHART_COLORS[idx % len(CHART_COLORS)]
        parts.append(
            '<article class="style-meter-card">'
            f'<div><strong>{html.escape(style["name"])}</strong><span>{html.escape(style["level"])}</span></div>'
            f'<div class="style-meter"><i style="width:{width}%;background:{html.escape(color)}"></i></div>'
            '</article>'
        )
    parts.append('</div></div>')
    return "\n".join(parts)


def render_value_visual(values: List[Dict[str, Any]]) -> str:
    if not values:
        return '<p class="muted">当前笔记证据不足，暂不生成价值观可视化。</p>'
    max_score = max((int(v.get("score") or 0) for v in values), default=1)
    parts = ['<div class="value-summary">']
    for idx, value in enumerate(values):
        score = int(value.get("score") or 0)
        width = pct_bar(score, max_score)
        color = CHART_COLORS[idx % len(CHART_COLORS)]
        parts.append(
            '<article class="value-card">'
            f'<div class="value-orbit" style="--value-color:{html.escape(color)};--value-pct:{width}%"><span>{width}</span></div>'
            f'<div class="value-card-copy"><strong>{html.escape(value["name"])}</strong>'
            f'<em>信号强度 {score}</em>'
            f'<div class="value-track"><div style="width:{width}%;background:{html.escape(color)}"></div></div></div>'
            '</article>'
        )
    parts.append('</div>')
    return "\n".join(parts)


def render_people_visual(people: List[Tuple[str, int]]) -> str:
    if not people:
        return '<p class="muted">当前作者/人物线索不足，暂不生成人物分布图。</p>'
    top = people[:8]
    chart = render_donut_chart(
        "人物/作者关注分布",
        [
            {
                "label": name,
                "value": count,
                "display": str(count),
                "color": CHART_COLORS[idx % len(CHART_COLORS)],
            }
            for idx, (name, count) in enumerate(top)
        ],
        "人物",
        "代表阅读关注度，不等同于价值认同。",
    )
    tags = ['<div class="people-rank">']
    for idx, (name, count) in enumerate(top, 1):
        tags.append(
            '<span>'
            f'<b>{idx}</b>{html.escape(name)}<em>{count}</em>'
            '</span>'
        )
    tags.append('</div>')
    return '<div class="people-visual">' + chart + "\n".join(tags) + '</div>'


def render_html(report: Dict[str, Any], template_path: Path) -> str:
    b = report["basis"]
    body: List[str] = []
    chunk: List[str] = []
    chunk.append('<div class="metric-stack"><div class="metric-grid metric-grid-primary">')
    chunk.append(metric("累计阅读", b["totalReadTime"]))
    chunk.append(metric("有效阅读天数", b["readDays"] if b["daysAvailable"] else "未获取"))
    chunk.append(metric("读过/读完", f"{b['booksRead']} / {b['booksFinished']}" if b["bookCountsAvailable"] else "未获取"))
    chunk.append(metric("官方笔记口径", b["notes"] if b["notesAvailable"] else "未获取"))
    chunk.append('</div><div class="metric-grid metric-grid-secondary">')
    chunk.append(metric("书架可见条目", b["shelfTotal"]))
    chunk.append(metric("导出划线/想法", f"{b['exportedUnderlines']} / {b['exportedReviews']}"))
    chunk.append(metric("进度/书籍详情", f"{b['progressRows']} / {b['bookInfoRows']}"))
    chunk.append("</div></div>")
    basis_charts = render_basis_charts(b)
    if basis_charts:
        chunk.append(basis_charts)
    if b["limited"]:
        chunk.append('<p class="muted">注意：本次使用了 --max-note-books，为抽样导出，不代表完整笔记画像。</p>')
    chunk.append('<h3>数据覆盖情况</h3>')
    chunk.extend(f'<p class="muted">{html.escape(line)}</p>' for line in coverage_lines(report["coverage"]))
    body.append(section("数据基础", "\n".join(chunk), "basis", "featured"))
    if report.get("llmAnalysis"):
        body.append(semantic_html(report['llmAnalysis']))

    chunk = []
    map_charts = render_map_charts(report)
    if map_charts:
        chunk.append(map_charts)
    if report["annual"]:
        chunk.append("<h3>年度阅读</h3>")
        max_h = max((y["hours"] for y in report["annual"]), default=1)
        for y in report["annual"]:
            if y["hours"] > 0 or y["readDays"] > 0:
                chunk.append(render_bar(str(y["year"]), y["hours"], max_h, "h"))
    if report["categories"]:
        chunk.append("<h3>分类偏好</h3>")
        max_h = max((c["hours"] for c in report["categories"]), default=1)
        for c in report["categories"]:
            chunk.append(render_bar(c["name"], c["hours"], max_h, "h"))
    if report["topNoteBooks"]:
        chunk.append("<h3>笔记最多的书</h3><ul>")
        for r in report["topNoteBooks"][:8]:
            chunk.append(f"<li>{html.escape(r['title'])}：{r['notes']} 条</li>")
        chunk.append("</ul>")
    body.append(section("阅读地图", "\n".join(chunk), "map"))

    chunk = []
    chunk.append(render_theme_overview(report["themes"]))
    max_score = max((t["score"] for t in report["themes"]), default=1)
    for theme in report["themes"]:
        chunk.append(f"<h3>{html.escape(theme['name'])}</h3>")
        chunk.append(render_bar("信号强度", theme["score"], max_score))
        chunk.append(f"<p><strong>核心问题：</strong>{html.escape(theme['question'])}</p>")
        chunk.append(f'<p class="muted">{html.escape(theme["source"])}</p>')
        for ev in theme["evidence"]:
            chunk.append(quote_html(ev))
    body.append(section("主题与问题意识", "\n".join(chunk), "themes"))

    chunk = []
    chunk.append(render_thinking_overview(report["styles"]))
    max_style_score = max((s["score"] for s in report["styles"]), default=1)
    for style in report["styles"][:5]:
        chunk.append(f"<h3>{html.escape(style['name'])}</h3>")
        chunk.append(render_bar(f"{style['level']} · 信号强度", style["score"], max_style_score))
        for ev in style["evidence"]:
            chunk.append(quote_html(ev))
    body.append(section("思考方式", "\n".join(chunk), "thinking"))

    body.append(section("价值观、焦虑与长期方向", '<p class="muted">以下仅为个人点评中的词汇关注信号，不确认价值认同、焦虑来源或长期方向。</p>' + render_value_visual(report["values"]), "values"))

    if report["people"]:
        body.append(section("人物/作者线索", render_people_visual(report["people"]), "people"))

    chunk = [render_profile_visual(report)]
    chunk.append('<div class="portrait-copy">')
    for p in report["portrait"]:
        chunk.append(f"<p>{html.escape(p)}</p>")
    chunk.append('</div>')
    body.append(section("读者画像", "\n".join(chunk), "portrait", "featured"))

    body.append(section("信息茧房", render_information_cocoon(report["informationCocoon"]), "cocoon", "cocoon"))
    body.append(section("推荐书单", render_book_cards(report["recommendedBooks"]), "books", "books"))

    chunk = [f'<div class="roast-note">{html.escape(report["strictNotice"])}</div>']
    chunk.append('<div class="two-col">')
    chunk.append('<div class="mini-card"><h3>严格诊断</h3><ul>')
    for item in report["strictProfile"]:
        chunk.append(f"<li>{html.escape(item)}</li>")
    chunk.append("</ul></div>")
    chunk.append('<div class="mini-card"><h3>可能的盲区</h3><ul>')
    for item in report["blindSpots"]:
        chunk.append(f"<li>{html.escape(item)}</li>")
    chunk.append("</ul></div></div>")
    chunk.append("<h3>维度打分</h3>")
    max_score = 100
    for item in report["dimensionScores"]:
        if item["score"] is None:
            chunk.append(f'<p><strong>{html.escape(item["name"])}</strong>：暂不评分（证据不足）</p>')
        else:
            chunk.append(render_bar(item["name"], item["score"], max_score, "/100"))
        chunk.append(f'<p class="muted">{html.escape(item["note"])}</p>')
    body.append(section("温馨提示：下面可能有一点刺耳", "\n".join(chunk), "roast", "roast"))

    chunk = []
    for title, items in report["suggestions"].items():
        chunk.append(f'<div class="advice-group"><h3>{html.escape(title)}</h3><ul>')
        for item in items:
            chunk.append(f"<li>{html.escape(item)}</li>")
        chunk.append("</ul></div>")
    chunk.append("<h3>更严格的执行建议</h3>")
    chunk.append('<div class="advice-grid">')
    for title, items in report["sharperAdvice"].items():
        chunk.append(f'<div class="mini-card compact"><h3>{html.escape(title)}</h3><ul>')
        for item in items:
            chunk.append(f"<li>{html.escape(item)}</li>")
        chunk.append("</ul></div>")
    chunk.append("</div>")
    body.append(section("建议", "\n".join(chunk), "advice"))

    template = template_path.read_text(encoding="utf-8")
    summary = report["profileSummary"]
    if report.get("llmAnalysis"):
        summary = {"label": "大模型增强阅读报告", "tagline": "语义结论、原始证据与本地统计分别呈现；分析范围见数据覆盖说明。"}
    return (
        template
        .replace("{{TITLE}}", html.escape(report["title"]))
        .replace("{{PROFILE_LABEL}}", html.escape(summary["label"]))
        .replace("{{PROFILE_TAGLINE}}", html.escape(summary["tagline"]))
        .replace("{{SUBTITLE}}", html.escape(f"生成时间：{report['generatedAt']}。{report['coverage']['scope']}。"))
        .replace("{{BODY}}", "\n".join(body))
    )
