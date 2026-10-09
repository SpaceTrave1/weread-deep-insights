"""Deterministic analysis of local records; no network or credential access."""
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional, Tuple
import re
from collections import Counter
if __package__:
    from .common import CN_TZ, as_list, clean_text, truncate, seconds_text, date_text, ts_for_year, stat_counts, notebook_total, valid_records
    from .coverage import build_coverage
else:
    from common import CN_TZ, as_list, clean_text, truncate, seconds_text, date_text, ts_for_year, stat_counts, notebook_total, valid_records
    from coverage import build_coverage

THEMES = {
    "制度、权力与社会运行": {
        "keywords": ["制度", "权力", "政府", "政治", "国家", "治理", "政策", "稳定", "公平", "效率", "阶级", "利益", "官僚"],
        "question": "制度如何塑造普通人的选择，权力如何在现实中运作？",
    },
    "历史记忆与现实解释": {
        "keywords": ["历史", "时代", "明朝", "传统", "周期", "人物", "记忆", "昨天", "来处", "兴衰", "改革"],
        "question": "历史中的人物、制度和命运，怎样帮助理解当下？",
    },
    "经济发展与地方现实": {
        "keywords": ["经济", "发展", "城市", "地方", "财政", "产业", "市场", "房地产", "收入", "分配", "贫富", "项目"],
        "question": "发展如何发生，代价由谁承担，收益如何分配？",
    },
    "科学、技术与文明探索": {
        "keywords": ["科学", "技术", "研究", "宇宙", "文明", "AI", "人工智能", "生命", "物理", "创新", "探索", "工程"],
        "question": "技术进步和科学探索会把人类带向哪里？",
    },
    "个人成长与行动原则": {
        "keywords": ["成长", "习惯", "行动", "自律", "目标", "责任", "方向", "努力", "选择", "挑战", "主动", "原则"],
        "question": "个体如何在不确定环境里保持能动性和持续成长？",
    },
    "家庭、关系与情感连接": {
        "keywords": ["家庭", "父母", "家人", "朋友", "亲戚", "沟通", "理解", "情感", "安全感", "孤独", "爱", "关系"],
        "question": "亲密关系、家庭记忆和沟通方式如何影响一个人？",
    },
    "信息环境与公共表达": {
        "keywords": ["信息", "媒体", "舆论", "真相", "网络", "观点", "事实", "自媒体", "茧房", "二极管", "表达"],
        "question": "在复杂信息环境里，怎样接近事实并保持判断力？",
    },
    "文学、人性与存在感受": {
        "keywords": ["文学", "小说", "讽刺", "人性", "命运", "孤独", "荒诞", "尊严", "自由", "爱情", "生活"],
        "question": "文学如何照见人性、孤独、尊严和时代？",
    },
    "身体健康与生活秩序": {
        "keywords": ["健康", "身体", "运动", "睡眠", "饮食", "焦虑", "内耗", "压力", "心理", "养生"],
        "question": "如何把认知和生活方式落到稳定、健康的日常里？",
    },
}


THINKING_STYLES = {
    "理性分析": ["逻辑", "机制", "结构", "原因", "结果", "数据", "论文", "模型", "客观", "推导", "比较"],
    "批判辨析": ["批判", "质疑", "荒谬", "误导", "真相", "二极管", "舆论", "权力", "利益", "政治正确"],
    "现实导向": ["现实", "落实", "项目", "地方", "政策", "生活", "工作", "行动", "可行", "代价"],
    "成长导向": ["成长", "习惯", "自律", "目标", "方向", "挑战", "责任", "主动", "复盘", "坚持"],
    "技术/科学导向": ["科学", "技术", "AI", "工程", "研究", "宇宙", "生命", "创新", "搜索引擎"],
    "情感共鸣": ["孤独", "爱", "家庭", "朋友", "理解", "情感", "安全感", "记忆", "共情"],
}


VALUE_SIGNALS = {
    "真相与独立判断": ["真相", "事实", "信息", "判断", "观点", "茧房", "误导"],
    "责任与主观能动性": ["责任", "主动", "能动性", "行动", "选择", "努力"],
    "公共生活与国家发展": ["国家", "社会", "发展", "政府", "制度", "公共", "人民"],
    "科学精神与长期探索": ["科学", "研究", "创新", "探索", "技术", "文明"],
    "关系中的真诚沟通": ["沟通", "理解", "家人", "朋友", "承诺", "真诚"],
    "健康稳定的生活秩序": ["健康", "运动", "睡眠", "焦虑", "内耗", "身体", "压力"],
}


PEOPLE_SEEDS: List[str] = []












































def score_text(text: str, keywords: Iterable[str]) -> int:
    return sum(text.count(k) for k in keywords)


def content_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for book in data["notebooks"]["bookNotes"]:
        for review in valid_records(book, "reviews"):
            text = clean_text(review.get("content"))
            if text and not review.get("error"):
                items.append({
                    "kind": "personal_review",
                    "bookId": book.get("bookId") or book["title"],
                    "weight": 3,
                    "title": book["title"],
                    "author": book.get("author", ""),
                    "text": text,
                    "chapter": clean_text(review.get("chapterName")),
                    "time": review.get("createTime"),
                })
        for underline in valid_records(book, "underlines"):
            text = clean_text(underline.get("text"))
            if text and not underline.get("error"):
                items.append({
                    "kind": "underline",
                    "bookId": book.get("bookId") or book["title"],
                    "weight": 1,
                    "title": book["title"],
                    "author": book.get("author", ""),
                    "text": text,
                    "chapter": clean_text(underline.get("chapterTitle")),
                    "time": underline.get("createTime"),
                })
    return items


def pick_evidence(items: List[Dict[str, Any]], keywords: Iterable[str], used: set, limit: int = 2) -> List[Dict[str, str]]:
    ranked: List[Tuple[int, Dict[str, Any]]] = []
    for item in items:
        text = item["text"]
        score = score_text(text, keywords)
        if score <= 0:
            continue
        if item["kind"] == "personal_review":
            score += 5
        if len(text) > 35:
            score += 1
        ranked.append((score, item))
    ranked.sort(key=lambda x: x[0], reverse=True)
    evidence: List[Dict[str, str]] = []
    for _, item in ranked:
        key = (item["title"], item["text"][:80])
        if key in used:
            continue
        used.add(key)
        evidence.append({
            "title": item["title"],
            "kind": "想法" if item["kind"] == "personal_review" else "划线",
            "text": truncate(item["text"], 220),
        })
        if len(evidence) >= limit:
            break
    return evidence


def normalized_author(author: str) -> List[str]:
    cleaned = re.sub(r"[\[\]【】（）()［］]", " ", clean_text(author))
    parts = re.split(r"[、,，/|;；·\s]+", cleaned)
    result = []
    for p in parts:
        p = p.strip()
        if 2 <= len(p) <= 8 and p not in {"著", "编著", "译", "作者", "美", "英", "法", "哥", "明"}:
            result.append(p)
    return result


def people_counter(data: Dict[str, Any], text_blob: str) -> List[Tuple[str, int]]:
    counter: Counter[str] = Counter()
    prefer = as_list(data["stats"]["overall"].get("preferAuthor"))
    for item in prefer:
        name = clean_text(item.get("name"))
        if name:
            counter[name] += int(item.get("count") or 1) * 3
    for book in as_list(data["notebooks"]["books"]):
        author = clean_text((book.get("book") or {}).get("author"))
        for name in normalized_author(author):
            counter[name] += 2
    for seed in PEOPLE_SEEDS:
        c = text_blob.count(seed)
        if c:
            counter[seed] += c
    return counter.most_common(12)


def family_for_text(text: str) -> str:
    probes = [
        ("public", ["制度", "权力", "社会", "政治", "公共", "治理", "国家"]),
        ("history", ["历史", "传统", "时代", "文明", "记忆"]),
        ("economy", ["经济", "发展", "地方", "市场", "财政", "城市"]),
        ("science", ["科学", "技术", "AI", "人工智能", "工程", "宇宙", "生命"]),
        ("growth", ["成长", "自律", "行动", "目标", "习惯"]),
        ("relationship", ["家庭", "关系", "情感", "沟通", "父母", "朋友"]),
        ("information", ["信息", "媒体", "舆论", "真相", "表达", "网络"]),
        ("literature", ["文学", "小说", "人性", "存在", "命运", "自由"]),
        ("health", ["健康", "身体", "睡眠", "运动", "心理", "压力"]),
    ]
    for family, keywords in probes:
        if any(k in text for k in keywords):
            return family
    return "general"


def build_profile_summary(primary_themes: List[str], primary_styles: List[str], top_cat_share: int, idea_ratio: int,
                          evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not evidence or not evidence.get("personalSufficient") or not primary_styles:
        return {"label": "画像证据不足", "tagline": "暂不归纳读者类型或稳定性格；关键词与书名只能提供文本线索。", "keywords": []}
    theme_text = "、".join(primary_themes[:2]) or "尚不足以归纳的主题"
    style_text = "、".join(primary_styles[:2])
    families = {family_for_text(t) for t in primary_themes}
    style_set = set(primary_styles)

    if {"public", "economy", "information"} & families and ("现实导向" in style_set or "批判辨析" in style_set):
        label = "现实解释者"
    elif "science" in families or "技术/科学导向" in style_set:
        label = "技术探索者"
    elif "literature" in families or "情感共鸣" in style_set:
        label = "人性观察者"
    elif "growth" in families or "成长导向" in style_set:
        label = "自我迭代者"
    elif "批判辨析" in style_set or "理性分析" in style_set:
        label = "问题拆解者"
    else:
        label = "文本问题关注者"

    return {
        "label": label,
        "tagline": f"仅在本次有效个人点评中，观察到{theme_text}与{style_text}相关词汇。标签是文本归纳，不能确认动机、认同或性格。",
        "keywords": [x for x in [label, *primary_styles[:2], *primary_themes[:2]] if x],
    }


def build_information_cocoon(
    categories: List[Dict[str, Any]],
    theme_rows: List[Dict[str, Any]],
    top_cat_share: int,
    top_theme_share: int,
    idea_ratio: int,
    evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    category_ok = bool(evidence and evidence.get("categorySufficient"))
    theme_ok = bool(evidence and evidence.get("themeSufficient"))
    if not category_ok and not theme_ok:
        return {"level": "证据不足", "score": None,
                "summary": "缺少足量且覆盖明确的分类或笔记数据，暂不评估集中程度。阅读记录不能确认信息茧房。",
                "signals": ["分类需要至少 5 本的有效分类记录；主题需要完整笔记覆盖、至少 5 条匹配文本且来自至少 2 本书。"],
                "antidotes": ["可选练习：为一次阅读写下证据和反例；这不是对个人盲区的诊断。"]}
    shares = ([top_cat_share] if category_ok else []) + ([top_theme_share] if theme_ok else [])
    risk_score = round(sum(shares) / len(shares))
    if risk_score >= 68:
        level = "偏高"
    elif risk_score >= 42:
        level = "中等"
    else:
        level = "较低"

    top_category = categories[0]["name"] if categories else "暂无明显分类"
    top_theme = theme_rows[0]["name"] if theme_rows else "暂无明显主题"
    signals = []
    if category_ok:
        signals.append(f"最高阅读分类：{top_category}，约占接口返回分类阅读时长 {top_cat_share}%；接口分类可能不覆盖全部阅读。")
    if theme_ok:
        signals.append(f"最高主题：{top_theme}，约占已获取文本关键词加权信号 {top_theme_share}%；不同主题关键词可能重叠。")

    antidotes = []
    if max(shares) >= 35:
        antidotes.append("给最高频主题配一本真正反对它或绕开它的书，而不是只找补充材料。")
        antidotes.append("每月安排一次“异质阅读”：文学、自然科学、艺术、身体经验任选其一，目的不是有用，而是打断惯性。")
    else:
        antidotes.append("保留当前多元结构，但为最有潜力的一个问题建立长期书单，避免兴趣只停留在浅层采样。")
    antidotes.append("写笔记时加入一句“这条判断可能错在哪里”，让阅读系统自带反证入口。")

    return {
        "level": level,
        "score": risk_score,
        "summary": f"已获取数据的集中信号{level}。分数是可用最高占比的算术均值，不是心理量表或信息茧房概率；缺少反方接触和认同数据，不能确认信息茧房。",
        "signals": signals,
        "antidotes": antidotes,
    }


BOOK_RECOMMENDATION_POOL = [
    {"title": "乡土中国", "author": "费孝通", "family": "public", "lane": "补结构", "why": "用极短篇幅建立社会结构和基层秩序的基本框架。"},
    {"title": "叫魂", "author": "孔飞力", "family": "public", "lane": "反直觉", "why": "适合训练从事件进入制度、地方治理和群体心理的能力。"},
    {"title": "政治秩序与政治衰败", "author": "弗朗西斯·福山", "family": "public", "lane": "拉长尺度", "why": "把制度、国家能力和现代化放到更长周期里比较。"},
    {"title": "万历十五年", "author": "黄仁宇", "family": "history", "lane": "历史切片", "why": "用一年观察制度惯性、人物处境和时代结构。"},
    {"title": "历史的运用与滥用", "author": "尼采", "family": "history", "lane": "反省历史感", "why": "提醒历史阅读不要只服务现实解释，也要警惕被历史感吞没。"},
    {"title": "置身事内", "author": "兰小欢", "family": "economy", "lane": "现实机制", "why": "适合把地方政府、产业、财政和发展逻辑连起来看。"},
    {"title": "繁荣与衰退", "author": "艾伦·格林斯潘 / 阿德里安·伍德里奇", "family": "economy", "lane": "宏观补课", "why": "补充经济增长、制度和创新之间的宏观解释。"},
    {"title": "复杂", "author": "梅拉妮·米歇尔", "family": "science", "lane": "科学视角", "why": "适合把复杂系统思维引入社会、技术和个体问题。"},
    {"title": "技术与文明", "author": "刘易斯·芒福德", "family": "science", "lane": "技术批判", "why": "避免把技术只看成效率工具，转而看它如何改变生活结构。"},
    {"title": "非暴力沟通", "author": "马歇尔·卢森堡", "family": "relationship", "lane": "关系练习", "why": "把理解、表达和冲突处理从观念拉回具体话语。"},
    {"title": "爱的艺术", "author": "埃里希·弗洛姆", "family": "relationship", "lane": "情感结构", "why": "适合从关系、自由、成熟和责任角度理解亲密经验。"},
    {"title": "事实", "author": "汉斯·罗斯林", "family": "information", "lane": "校准判断", "why": "训练在公共信息中识别直觉偏差和数据误读。"},
    {"title": "娱乐至死", "author": "尼尔·波兹曼", "family": "information", "lane": "媒介反思", "why": "适合分析信息环境如何改变公共表达和注意力。"},
    {"title": "卡拉马佐夫兄弟", "author": "陀思妥耶夫斯基", "family": "literature", "lane": "人性深读", "why": "用文学复杂性对冲过快的机制解释。"},
    {"title": "局外人", "author": "阿尔贝·加缪", "family": "literature", "lane": "存在感受", "why": "适合训练不急着归因的阅读耐心。"},
    {"title": "我们为什么要睡觉", "author": "马修·沃克", "family": "health", "lane": "身体补课", "why": "提醒阅读和思考不能替代身体秩序。"},
    {"title": "运动改造大脑", "author": "约翰·瑞迪", "family": "health", "lane": "行动落地", "why": "把认知、情绪和生活习惯连接到可执行行动。"},
    {"title": "学会提问", "author": "尼尔·布朗 / 斯图尔特·基利", "family": "general", "lane": "思辨工具", "why": "适合把批判性从情绪反应升级为结构化提问。"},
    {"title": "风格感觉", "author": "史蒂文·平克", "family": "general", "lane": "写作升级", "why": "帮助把复杂判断写得更清楚，而不是只写得更用力。"},
]


def title_seen(title: str, read_titles: set) -> bool:
    compact = re.sub(r"\s+", "", title)
    for seen in read_titles:
        seen_compact = re.sub(r"\s+", "", seen)
        if compact and (compact in seen_compact or seen_compact in compact):
            return True
    return False


def build_recommended_books(
    primary_themes: List[str],
    primary_styles: List[str],
    categories: List[Dict[str, Any]],
    read_titles: set,
    cocoon: Dict[str, Any],
) -> List[Dict[str, str]]:
    if not primary_themes and not primary_styles and not categories:
        return []
    wanted = [family_for_text(t) for t in primary_themes]
    wanted.extend(family_for_text(c["name"]) for c in categories[:3])
    if "技术/科学导向" in primary_styles:
        wanted.append("science")
    if "情感共鸣" in primary_styles:
        wanted.append("relationship")
    if "批判辨析" in primary_styles or "理性分析" in primary_styles:
        wanted.append("general")
    if cocoon["level"] in {"中等", "偏高"}:
        wanted.extend(["literature", "health", "science", "relationship"])

    selected: List[Dict[str, str]] = []
    used_titles: set = set()

    def add_book(book: Dict[str, str], reason_prefix: str = "") -> None:
        if len(selected) >= 8 or book["title"] in used_titles or title_seen(book["title"], read_titles):
            return
        used_titles.add(book["title"])
        selected.append({
            "title": book["title"],
            "author": book["author"],
            "lane": book["lane"],
            "why": f"{reason_prefix}{book['why']}",
        })

    for family in wanted:
        for book in BOOK_RECOMMENDATION_POOL:
            if book["family"] == family:
                add_book(book)
                if len(selected) >= 5:
                    break
        if len(selected) >= 5:
            break

    for book in BOOK_RECOMMENDATION_POOL:
        if len(selected) >= 8:
            break
        prefix = "补盲用： " if cocoon["level"] in {"中等", "偏高"} and book["family"] not in set(wanted[:4]) else ""
        add_book(book, prefix)

    return selected


def build_personalized_suggestions(
    primary_themes: List[str],
    primary_styles: List[str],
    completion_rate: float,
    idea_ratio: int,
    cocoon: Dict[str, Any],
) -> Dict[str, List[str]]:
    theme = primary_themes[0] if primary_themes else "最高频问题"
    style = primary_styles[0] if primary_styles else "主要思考方式"
    reading = [
        f"围绕“{theme}”保留一条主线，但每 3 本同向书后插入 1 本异质书，专门挑战当前解释框架。",
        cocoon["antidotes"][0],
    ]
    writing = [
        f"把笔记整理成“原文触发-我的判断-证据-反例-暂时结论”五段式，尤其适合你当前的{style}。",
        "每月只选一个高频问题写成短文，少罗列书摘，多暴露自己的判断链条和不确定处。",
    ]
    thinking = [
        "可选练习：为一个判断写下反方最强版本和支持证据。",
        "可选练习：分别写出事实、机制解释和价值选择。",
    ]
    growth = ["可选练习：记录一次阅读后的具体行动与结果。", "可选练习：定期检查停读原因并调整书单。"]
    return {
        "阅读建议": reading,
        "写作建议": writing,
        "思考方式建议": thinking,
        "个人成长建议": growth,
    }


def build_execution_advice(cocoon: Dict[str, Any], primary_styles: List[str]) -> Dict[str, List[str]]:
    return {"通用可选练习（非个人诊断）": ["尝试记录一次阅读后的具体行动及结果；当前数据不能判断执行情况。"]}


def analyze(data: Dict[str, Any], title: str) -> Dict[str, Any]:
    overall = data["stats"]["overall"]
    counts = stat_counts(overall.get("readStat") or [])
    annual_rows = []
    for row in data["stats"]["annual"]:
        if row.get("fetchStatus") in {"failed", "not_requested"}:
            continue
        d = row["data"]
        annual_rows.append({
            "year": row["year"],
            "seconds": int(d.get("totalReadTime") or 0),
            "hours": round(int(d.get("totalReadTime") or 0) / 3600, 1),
            "readDays": int(d.get("readDays") or 0),
        })

    shelf_books = data["shelf"]["books"]
    albums = data["shelf"]["albums"]
    mp_count = 1 if data["shelf"]["raw"].get("mp") is not None else 0
    shelf_total = len(shelf_books) + len(albums) + mp_count
    notebooks = data["notebooks"]["books"]
    book_notes = data["notebooks"]["bookNotes"]
    items = content_items(data)
    text_blob = "\n".join([i["text"] for i in items])

    total_underlines = sum(len(valid_records(b, "underlines")) for b in book_notes)
    total_reviews = sum(len(valid_records(b, "reviews")) for b in book_notes)
    coverage = build_coverage(data, total_underlines, total_reviews)
    notebook_notes_total = sum(notebook_total(b) for b in notebooks)

    used_evidence: set = set()
    theme_rows = []
    for name, spec in THEMES.items():
        score = 0
        for item in items:
            score += score_text(item["text"], spec["keywords"]) * item["weight"]
        for book in book_notes:
            title_author = f"{book.get('title','')} {book.get('author','')}"
            score += score_text(title_author, spec["keywords"]) * 2
        if score > 0:
            theme_rows.append({
                "name": name,
                "score": score,
                "question": spec["question"],
                "evidence": pick_evidence(items, spec["keywords"], used_evidence, limit=2),
                "matchedItems": sum(score_text(i["text"], spec["keywords"]) > 0 for i in items),
                "matchedBookCount": len({i["bookId"] for i in items if score_text(i["text"], spec["keywords"]) > 0}),
                "personalMatchedItems": sum(i["kind"] == "personal_review" and score_text(i["text"], spec["keywords"]) > 0 for i in items),
                "personalBookCount": len({i["bookId"] for i in items if i["kind"] == "personal_review" and score_text(i["text"], spec["keywords"]) > 0}),
                "source": "文本及书名关键词线索，不能据此确认认同",
            })
    theme_rows.sort(key=lambda x: x["score"], reverse=True)

    style_rows = []
    style_used_evidence: set = set()
    for name, keywords in THINKING_STYLES.items():
        score = 0
        hits = 0
        review_hits = 0
        underline_hits = 0
        book_hits: set = set()
        review_books: set = set()
        review_items = 0
        for item in items:
            item_hits = score_text(item["text"], keywords)
            if item_hits <= 0:
                continue
            hits += item_hits
            if item["kind"] == "personal_review":
                review_hits += item_hits
                review_books.add(item["bookId"])
                review_items += 1
            else:
                underline_hits += item_hits
            book_hits.add(item["bookId"])
            score += item_hits * item["weight"]
        if score > 0:
            style_rows.append({
                "name": name,
                "score": score,
                "hits": hits,
                "reviewHits": review_hits,
                "underlineHits": underline_hits,
                "bookCount": len(book_hits),
                "personalSufficient": review_items >= 3 and len(review_books) >= 2,
                "evidence": pick_evidence([i for i in items if i["kind"] == "personal_review"] if review_items >= 3 and len(review_books) >= 2 else items,
                                          keywords, style_used_evidence, limit=1),
            })
    style_rows.sort(key=lambda x: x["score"], reverse=True)
    max_style_score = max((s["score"] for s in style_rows), default=1)
    for row in style_rows:
        row["normalized"] = max(1, min(100, round(row["score"] / max_style_score * 100)))
        if not row["personalSufficient"]:
            row["level"] = "仅文本线索，个人证据不足"
        elif row["normalized"] >= 75:
            row["level"] = "强信号"
        elif row["normalized"] >= 45:
            row["level"] = "中信号"
        else:
            row["level"] = "弱信号"

    value_rows = []
    value_used_evidence: set = set()
    for name, keywords in VALUE_SIGNALS.items():
        score = 0
        matching_reviews = [i for i in items if i["kind"] == "personal_review" and score_text(i["text"], keywords) > 0]
        for item in matching_reviews:
            score += score_text(item["text"], keywords) * item["weight"]
        if score >= 15 and len(matching_reviews) >= 3 and len({i["bookId"] for i in matching_reviews}) >= 2:
            value_rows.append({
                "name": name,
                "score": score,
                "evidence": pick_evidence(matching_reviews, keywords, value_used_evidence, limit=1),
            })
    value_rows.sort(key=lambda x: x["score"], reverse=True)

    categories = []
    for cat in as_list(overall.get("preferCategory")):
        seconds = int(cat.get("readingTime") or 0)
        if seconds > 0:
            categories.append({
                "name": clean_text(cat.get("categoryTitle")),
                "parent": clean_text(cat.get("parentCategoryTitle")),
                "seconds": seconds,
                "hours": round(seconds / 3600, 1),
                "books": int(cat.get("readingCount") or 0),
            })
    categories.sort(key=lambda x: x["seconds"], reverse=True)

    top_note_books = []
    for b in sorted(book_notes, key=lambda x: int(x.get("totalNotes") or 0), reverse=True)[:12]:
        top_note_books.append({
            "title": b["title"],
            "author": b.get("author", ""),
            "notes": b.get("totalNotes", 0),
            "reviews": b.get("reviewCount", 0),
            "underlines": b.get("underlineCount", 0),
        })

    read_longest = []
    for row in as_list(overall.get("readLongest"))[:10]:
        book = row.get("book") or {}
        album = row.get("albumInfo") or {}
        read_longest.append({
            "title": clean_text(book.get("title") or album.get("name") or "未知"),
            "author": clean_text(book.get("author") or album.get("authorName")),
            "seconds": int(row.get("readTime") or 0),
            "time": seconds_text(row.get("readTime")),
        })

    people = people_counter(data, text_blob)

    primary_styles = [s["name"] for s in style_rows if s["personalSufficient"]][:3]
    primary_themes = [t["name"] for t in theme_rows if t["personalMatchedItems"] >= 3 and t["personalBookCount"] >= 2][:4]

    completion_rate = round(counts.get("读完", 0) / counts.get("读过", 1) * 100, 1) if counts.get("读过", 0) else 0
    idea_ratio = round(total_reviews / max(total_reviews + total_underlines, 1) * 100)
    top_cat_share = 0
    if categories:
        top_cat_share = round(categories[0]["seconds"] / max(sum(c["seconds"] for c in categories), 1) * 100)
    top_theme_share = 0
    if theme_rows:
        top_theme_share = round(theme_rows[0]["score"] / max(sum(t["score"] for t in theme_rows), 1) * 100)
    unfinished_books = max(counts.get("读过", 0) - counts.get("读完", 0), 0)
    read_titles = set()
    for book in shelf_books:
        title_text = clean_text(book.get("title"))
        if title_text:
            read_titles.add(title_text)
    for book in book_notes:
        title_text = clean_text(book.get("title"))
        if title_text:
            read_titles.add(title_text)
    for notebook in notebooks:
        title_text = clean_text((notebook.get("book") or {}).get("title"))
        if title_text:
            read_titles.add(title_text)

    personal_items = [i for i in items if i["kind"] == "personal_review"]
    overall_status = data.get("collectionStatus", {}).get("overall")
    overall_ok = overall_status not in {"failed", "empty", "not_requested"} and bool(overall)
    category_ok = overall_ok and sum(c["books"] for c in categories) >= 5 and bool(categories)
    completion_ok = (overall_ok and counts.get("读过", 0) >= 5 and "读完" in counts
                     and 0 <= counts["读完"] <= counts["读过"])
    ratio_ok = coverage["notesComplete"] and total_reviews + total_underlines >= 5
    evidence = {
        "personalSufficient": len(personal_items) >= 5 and len({i["bookId"] for i in personal_items}) >= 2,
        "categorySufficient": category_ok,
        "themeSufficient": (coverage["notesComplete"] and data["limits"].get("maxNoteBooks") is None
                            and len(items) >= 5 and len({i["bookId"] for i in items}) >= 2
                            and bool(theme_rows) and theme_rows[0]["matchedItems"] >= 5
                            and theme_rows[0]["matchedBookCount"] >= 2),
    }
    profile_summary = build_profile_summary(primary_themes, primary_styles, top_cat_share, idea_ratio, evidence)
    information_cocoon = build_information_cocoon(categories, theme_rows, top_cat_share, top_theme_share, idea_ratio, evidence)
    recommended_books = build_recommended_books(primary_themes, primary_styles, categories, read_titles, information_cocoon)

    portrait = [
        profile_summary["tagline"],
        f"证据范围：{len(personal_items)} 条有效个人点评，来自 {len({i['bookId'] for i in personal_items})} 本书；{coverage['scope']}。",
        "划线是选择的原文，不等于本人主张；关键词不能识别否定、讽刺或引用，也不能诊断焦虑或稳定性格。",
    ]

    strict_notice = "以下仅核对可观察指标；不足的数据不作诊断，分数不代表人格、能力或真实行动。"
    strict_profile = []
    if completion_ok:
        strict_profile.append(f"官方完读比例 {completion_rate}%（{counts['读完']}/{counts['读过']}）；无法由此确认收尾纪律或停读原因。")
    if total_reviews + total_underlines:
        strict_profile.append(f"本次有效点评占比 {idea_ratio}%（{total_reviews}/{total_reviews + total_underlines}），仅指已取得文本，不代表表达质量或全账户比例。")
    if category_ok:
        strict_profile.append(f"第一分类占返回分类时长约 {top_cat_share}%；这是分类集中信号，不能推断对陌生领域的态度。")
    if not strict_profile:
        strict_profile.append("证据不足，暂不作个人诊断。")

    blind_spots = []
    if category_ok and top_cat_share >= 50:
        blind_spots.append(f"可核查的覆盖风险：第一分类占返回分类时长 {top_cat_share}%。可选读其他领域对照；这不证明知识盲区。")
    if completion_ok and completion_rate < 50:
        blind_spots.append(f"可核查的未完读记录：官方读过与读完相差 {unfinished_books} 本；可检查停读原因，不能据此认定拖延。")
    if not blind_spots:
        blind_spots.append("没有足够证据识别个人盲区；真实行动、反方接触与理解质量未被采集。")

    dimension_scores = [
        {"name": "问题意识", "score": None, "note": "关键词不能衡量提问质量，暂不评分。"},
        {"name": "现实敏感度", "score": None, "note": "缺少现实行为验证，暂不评分。"},
        {"name": "表达密度", "score": idea_ratio if ratio_ok else None,
         "note": f"仅衡量有效点评/有效文本：{total_reviews}/{total_reviews + total_underlines}；需笔记覆盖完整且至少 5 条，不评价表达质量。"},
        {"name": "收尾纪律", "score": round(completion_rate) if completion_ok else None,
         "note": f"仅衡量官方读完/读过：{counts.get('读完', 0)}/{counts.get('读过', 0)}；需至少读过 5 本且计数有效，不评价纪律。"},
        {"name": "知识均衡", "score": 100 - top_cat_share if category_ok else None,
         "note": "仅衡量 100 减最高返回分类时长占比；需至少 5 本分类记录，不评价知识掌握或完整性。"},
        {"name": "行动落地", "score": None, "note": "未采集实际执行结果，暂不评分。"},
    ]

    suggestions = build_personalized_suggestions(
        primary_themes,
        primary_styles,
        completion_rate,
        idea_ratio,
        information_cocoon,
    )
    if not evidence["personalSufficient"]:
        suggestions = {"通用可选练习（非个人诊断）": ["写下阅读中的一个问题、支持证据和反例。", "如需个人画像，可先补足个人点评证据。"]}
    sharper_advice = build_execution_advice(information_cocoon, primary_styles)

    return {
        "title": title,
        "generatedAt": data["generatedAt"],
        "profileSummary": profile_summary,
        "coverage": coverage,
        "evidenceConditions": evidence,
        "basis": {
            "totalReadTime": seconds_text(overall.get("totalReadTime")) if overall_ok and "totalReadTime" in overall else "未获取",
            "officialStatsAvailable": overall_ok,
            "timeAvailable": overall_ok and "totalReadTime" in overall,
            "daysAvailable": overall_ok and "readDays" in overall,
            "bookCountsAvailable": overall_ok and "读过" in counts and "读完" in counts,
            "notesAvailable": overall_ok and "笔记" in counts,
            "readDays": int(overall.get("readDays") or 0),
            "booksRead": counts.get("读过", 0),
            "booksFinished": counts.get("读完", 0),
            "notes": counts.get("笔记", notebook_notes_total),
            "shelfTotal": shelf_total,
            "shelfBooks": len(shelf_books),
            "albums": len(albums),
            "mpCount": mp_count,
            "notebookBooks": len(notebooks),
            "exportedBooks": len(book_notes),
            "exportedUnderlines": total_underlines,
            "exportedReviews": total_reviews,
            "progressRows": sum(not r.get("error") and r.get("fetchStatus", "success") == "success" for r in data["shelf"]["progress"]),
            "bookInfoRows": sum(not r.get("error") and r.get("fetchStatus", "success") == "success" for r in data["shelf"].get("bookInfo") or []),
            "limited": data["limits"]["maxNoteBooks"] is not None,
        },
        "annual": annual_rows,
        "categories": categories[:10],
        "readLongest": read_longest,
        "topNoteBooks": top_note_books,
        "themes": theme_rows[:8],
        "questions": [t["question"] for t in theme_rows if t["matchedItems"] >= 3][:6],
        "styles": style_rows[:6],
        "values": value_rows[:6],
        "people": people,
        "portrait": portrait,
        "strictNotice": strict_notice,
        "strictProfile": strict_profile,
        "blindSpots": blind_spots,
        "dimensionScores": dimension_scores,
        "informationCocoon": information_cocoon,
        "recommendedBooks": recommended_books,
        "sharperAdvice": sharper_advice,
        "suggestions": suggestions,
    }
