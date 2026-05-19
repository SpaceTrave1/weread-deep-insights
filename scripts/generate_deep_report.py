#!/usr/bin/env python3
"""Generate deep WeRead reading profile reports.

Outputs HTML and/or Markdown from full personal WeRead records and notes.
The implementation uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


API_URL = "https://i.weread.qq.com/api/agent/gateway"
SKILL_VERSION = "1.0.3"
CN_TZ = timezone(timedelta(hours=8))


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


def load_env() -> None:
    """Load key=value pairs from nearby .env files without external packages."""
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[1] / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ]
    for path in candidates:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def post_json(url: str, body: Dict[str, Any], headers: Dict[str, str], timeout: int) -> Dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read().decode("utf-8")
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise RuntimeError("Unexpected non-object API response")
    return parsed


class WeReadClient:
    def __init__(self, api_key: str, timeout: int = 20, retries: int = 3):
        self.api_key = api_key
        self.timeout = timeout
        self.retries = retries
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def fetch(self, api_name: str, **params: Any) -> Dict[str, Any]:
        body = {"api_name": api_name, "skill_version": SKILL_VERSION, **params}
        last_error: Optional[BaseException] = None
        for attempt in range(self.retries):
            try:
                data = post_json(API_URL, body, self.headers, self.timeout)
                if data.get("upgrade_info"):
                    msg = data["upgrade_info"].get("message") or json.dumps(data["upgrade_info"], ensure_ascii=False)
                    raise RuntimeError(f"WeRead skill upgrade required: {msg}")
                if data.get("errcode"):
                    msg = data.get("errmsg") or data.get("message") or "unknown error"
                    raise RuntimeError(f"API {api_name} failed: {data.get('errcode')} {msg}")
                return data
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
                last_error = exc
                if attempt + 1 >= self.retries:
                    break
                time.sleep(0.6 * (attempt + 1))
        raise RuntimeError(f"API {api_name} failed after retries: {last_error}") from last_error


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def truncate(text: str, limit: int = 180) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def seconds_text(seconds: Any) -> str:
    try:
        seconds = int(seconds or 0)
    except (TypeError, ValueError):
        seconds = 0
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours:
        return f"{hours} 小时 {minutes} 分钟"
    return f"{minutes} 分钟"


def date_text(ts: Any) -> str:
    try:
        value = int(ts or 0)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    return datetime.fromtimestamp(value, CN_TZ).strftime("%Y-%m-%d")


def ts_for_year(year: int) -> int:
    return int(datetime(year, 6, 15, tzinfo=CN_TZ).timestamp())


def stat_counts(stats: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for item in stats or []:
        name = clean_text(item.get("stat"))
        counts = clean_text(item.get("counts"))
        found = re.search(r"\d+", counts.replace(",", ""))
        result[name] = int(found.group(0)) if found else 0
    return result


def notebook_total(book: Dict[str, Any]) -> int:
    return int(book.get("reviewCount") or 0) + int(book.get("noteCount") or 0) + int(book.get("bookmarkCount") or 0)


def collect_notebooks(client: WeReadClient) -> List[Dict[str, Any]]:
    books: List[Dict[str, Any]] = []
    last_sort: Optional[int] = None
    for _ in range(300):
        payload: Dict[str, Any] = {"count": 100}
        if last_sort is not None:
            payload["lastSort"] = last_sort
        page = client.fetch("/user/notebooks", **payload)
        page_books = as_list(page.get("books"))
        books.extend(page_books)
        if int(page.get("hasMore") or 0) != 1 or not page_books:
            break
        last_sort = page_books[-1].get("sort")
        if last_sort is None:
            break
    return books


def collect_reviews(client: WeReadClient, book_id: str) -> List[Dict[str, Any]]:
    reviews: List[Dict[str, Any]] = []
    synckey = 0
    for _ in range(100):
        page = client.fetch("/review/list/mine", bookid=book_id, count=100, synckey=synckey)
        for item in as_list(page.get("reviews")):
            review = item.get("review") or {}
            if review.get("content"):
                reviews.append(review)
        if int(page.get("hasMore") or 0) != 1:
            break
        next_key = page.get("synckey")
        if next_key is None or next_key == synckey:
            break
        synckey = next_key
    return reviews


def collect_book_notes(client: WeReadClient, notebooks: List[Dict[str, Any]], max_books: Optional[int]) -> List[Dict[str, Any]]:
    selected = sorted(notebooks, key=notebook_total, reverse=True)
    if max_books is not None:
        selected = selected[:max_books]

    result: List[Dict[str, Any]] = []
    for idx, item in enumerate(selected, 1):
        book = item.get("book") or {}
        book_id = str(item.get("bookId") or book.get("bookId") or "")
        if not book_id:
            continue
        sys.stderr.write(f"[{idx}/{len(selected)}] fetching notes: {book.get('title') or book_id}\n")
        underlines: List[Dict[str, Any]] = []
        chapters: Dict[str, str] = {}
        try:
            bookmark_data = client.fetch("/book/bookmarklist", bookId=book_id)
            for ch in as_list(bookmark_data.get("chapters")):
                chapters[str(ch.get("chapterUid"))] = clean_text(ch.get("title"))
            for row in as_list(bookmark_data.get("updated")):
                if row.get("markText"):
                    underlines.append({
                        "text": clean_text(row.get("markText")),
                        "chapterUid": row.get("chapterUid"),
                        "chapterTitle": chapters.get(str(row.get("chapterUid")), ""),
                        "createTime": row.get("createTime"),
                        "range": row.get("range"),
                    })
        except Exception as exc:  # keep the rest of the report available
            underlines.append({"text": f"[划线导出失败: {exc}]", "error": True})

        try:
            reviews = collect_reviews(client, book_id)
        except Exception as exc:
            reviews = [{"content": f"[个人点评导出失败: {exc}]", "error": True}]

        result.append({
            "bookId": book_id,
            "title": clean_text(book.get("title")) or book_id,
            "author": clean_text(book.get("author")),
            "reviewCount": int(item.get("reviewCount") or 0),
            "underlineCount": int(item.get("noteCount") or 0),
            "bookmarkCount": int(item.get("bookmarkCount") or 0),
            "totalNotes": notebook_total(item),
            "readingProgress": item.get("readingProgress"),
            "markedStatus": item.get("markedStatus"),
            "sort": item.get("sort"),
            "underlines": underlines,
            "reviews": reviews,
        })
    return result


def collect_progress(client: WeReadClient, shelf_books: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    progress: List[Dict[str, Any]] = []
    for idx, book in enumerate(shelf_books, 1):
        book_id = str(book.get("bookId") or "")
        if not book_id:
            continue
        try:
            data = client.fetch("/book/getprogress", bookId=book_id)
            row = data.get("book") or {}
            progress.append({
                "bookId": book_id,
                "title": clean_text(book.get("title")),
                "author": clean_text(book.get("author")),
                "progress": row.get("progress"),
                "recordReadingTime": row.get("recordReadingTime"),
                "updateTime": row.get("updateTime"),
                "finishTime": row.get("finishTime"),
            })
        except Exception as exc:
            progress.append({"bookId": book_id, "title": clean_text(book.get("title")), "error": str(exc)})
        if idx % 25 == 0:
            sys.stderr.write(f"progress fetched: {idx}/{len(shelf_books)}\n")
    return progress


def collect_book_info(client: WeReadClient, books: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    info_rows: List[Dict[str, Any]] = []
    seen: set = set()
    book_list = list(books)
    for idx, book in enumerate(book_list, 1):
        book_id = str(book.get("bookId") or (book.get("book") or {}).get("bookId") or "")
        if not book_id or book_id in seen:
            continue
        seen.add(book_id)
        try:
            info = client.fetch("/book/info", bookId=book_id)
            info_rows.append(info)
        except Exception as exc:
            info_rows.append({"bookId": book_id, "title": clean_text(book.get("title") or (book.get("book") or {}).get("title")), "error": str(exc)})
        if idx % 25 == 0:
            sys.stderr.write(f"book info fetched: {idx}/{len(book_list)}\n")
    return info_rows


def collect_data(args: argparse.Namespace) -> Dict[str, Any]:
    load_env()
    api_key = os.environ.get("WEREAD_API_KEY")
    if not api_key:
        raise SystemExit("WEREAD_API_KEY is not set. Set it in the environment or a local .env file.")

    client = WeReadClient(api_key, timeout=args.timeout, retries=args.retries)
    sys.stderr.write("fetching reading statistics...\n")
    overall = client.fetch("/readdata/detail", mode="overall", baseTime=0)
    weekly = client.fetch("/readdata/detail", mode="weekly")
    monthly = client.fetch("/readdata/detail", mode="monthly")

    current_year = datetime.now(CN_TZ).year
    regist_ts = overall.get("registTime")
    start_year = datetime.fromtimestamp(int(regist_ts), CN_TZ).year if regist_ts else current_year
    annual: List[Dict[str, Any]] = []
    for year in range(start_year, current_year + 1):
        annual.append({"year": year, "data": client.fetch("/readdata/detail", mode="annually", baseTime=ts_for_year(year))})

    sys.stderr.write("fetching shelf...\n")
    shelf = client.fetch("/shelf/sync")
    shelf_books = as_list(shelf.get("books"))
    albums = as_list(shelf.get("albums"))
    progress = [] if args.skip_progress else collect_progress(client, shelf_books)

    sys.stderr.write("fetching notebooks...\n")
    notebooks = collect_notebooks(client)
    book_info_source = shelf_books + notebooks
    book_info = [] if args.skip_book_info else collect_book_info(client, book_info_source)
    book_notes = collect_book_notes(client, notebooks, args.max_note_books)

    return {
        "generatedAt": datetime.now(CN_TZ).isoformat(timespec="seconds"),
        "skillVersion": SKILL_VERSION,
        "stats": {"overall": overall, "weekly": weekly, "monthly": monthly, "annual": annual},
        "shelf": {"raw": shelf, "books": shelf_books, "albums": albums, "progress": progress, "bookInfo": book_info},
        "notebooks": {"books": notebooks, "bookNotes": book_notes},
        "limits": {"maxNoteBooks": args.max_note_books, "skipProgress": args.skip_progress, "skipBookInfo": args.skip_book_info},
    }


def score_text(text: str, keywords: Iterable[str]) -> int:
    return sum(text.count(k) for k in keywords)


def content_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for book in data["notebooks"]["bookNotes"]:
        for review in as_list(book.get("reviews")):
            text = clean_text(review.get("content"))
            if text and not review.get("error"):
                items.append({
                    "kind": "personal_review",
                    "weight": 3,
                    "title": book["title"],
                    "author": book.get("author", ""),
                    "text": text,
                    "chapter": clean_text(review.get("chapterName")),
                    "time": review.get("createTime"),
                })
        for underline in as_list(book.get("underlines")):
            text = clean_text(underline.get("text"))
            if text and not underline.get("error"):
                items.append({
                    "kind": "underline",
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


def build_profile_summary(primary_themes: List[str], primary_styles: List[str], top_cat_share: int, idea_ratio: int) -> Dict[str, Any]:
    theme_text = "、".join(primary_themes[:2]) or "多元阅读"
    style_text = "、".join(primary_styles[:2]) or "开放联想"
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
        label = "开放漫游者"

    if top_cat_share >= 38:
        balance_note = "主线很强，容易形成稳定解释框架。"
    elif top_cat_share <= 18 and primary_themes:
        balance_note = "兴趣较分散，适合从高频问题里挑一条长期主线。"
    else:
        balance_note = "阅读结构相对均衡，既有主线也保留了游牧空间。"

    if idea_ratio >= 35:
        expression_note = "笔记里个人判断密度较高。"
    elif idea_ratio <= 12:
        expression_note = "划线多于自我判断，后续可增加自己的结论。"
    else:
        expression_note = "摘录和个人想法比例较稳。"

    return {
        "label": label,
        "tagline": f"{theme_text}驱动，常以{style_text}处理文本。{balance_note}{expression_note}",
        "keywords": [x for x in [label, *primary_styles[:2], *primary_themes[:2]] if x],
    }


def build_information_cocoon(
    categories: List[Dict[str, Any]],
    theme_rows: List[Dict[str, Any]],
    top_cat_share: int,
    top_theme_share: int,
    idea_ratio: int,
) -> Dict[str, Any]:
    risk_score = min(100, round(top_cat_share * 1.2 + top_theme_share * 0.8 + (8 if idea_ratio >= 45 else 0)))
    if risk_score >= 68:
        level = "偏高"
    elif risk_score >= 42:
        level = "中等"
    else:
        level = "较低"

    top_category = categories[0]["name"] if categories else "暂无明显分类"
    top_theme = theme_rows[0]["name"] if theme_rows else "暂无明显主题"
    signals = [
        f"最高阅读分类：{top_category}，约占分类阅读时长 {top_cat_share}%。",
        f"最高主题：{top_theme}，约占主题信号 {top_theme_share}%。",
    ]
    if idea_ratio >= 45:
        signals.append(f"个人想法占比较高（约 {idea_ratio}%），优点是判断活跃，风险是过早确认自己的解释。")
    elif idea_ratio <= 12:
        signals.append(f"个人想法占比较低（约 {idea_ratio}%），风险不是观点过强，而是输入很多、输出判断偏少。")

    antidotes = []
    if top_cat_share >= 35 or top_theme_share >= 35:
        antidotes.append("给最高频主题配一本真正反对它或绕开它的书，而不是只找补充材料。")
        antidotes.append("每月安排一次“异质阅读”：文学、自然科学、艺术、身体经验任选其一，目的不是有用，而是打断惯性。")
    else:
        antidotes.append("保留当前多元结构，但为最有潜力的一个问题建立长期书单，避免兴趣只停留在浅层采样。")
    antidotes.append("写笔记时加入一句“这条判断可能错在哪里”，让阅读系统自带反证入口。")

    return {
        "level": level,
        "score": risk_score,
        "summary": f"信息茧房风险为{level}。这不是说你读得窄，而是提醒你：高频主题越能解释世界，越容易变成默认答案。",
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
        "强判断前先写一句反方最强版本；如果写不出来，说明暂时还没有资格下重判。",
        "区分事实、机制和价值选择，避免把“我不喜欢”包装成“这不合理”。",
    ]
    growth = [
        "把阅读后的自我要求改成一个 48 小时内能完成的小动作，否则它只是漂亮的精神库存。",
        "每月清理一次未读完书：停读、跳读、精读、重读四选一，别让书架替你背负焦虑。",
    ]
    if completion_rate >= 70:
        growth[1] = "你的完读纪律较强，下一步要练习及时止损：不值得读完的书，不必用完成感装点它。"
    if idea_ratio <= 12:
        writing[1] = "每读完一章至少写一句自己的判断，哪怕粗糙；输入很多但不下注，判断力不会自动生长。"
    return {
        "阅读建议": reading,
        "写作建议": writing,
        "思考方式建议": thinking,
        "个人成长建议": growth,
    }


def build_execution_advice(cocoon: Dict[str, Any], primary_styles: List[str]) -> Dict[str, List[str]]:
    style = primary_styles[0] if primary_styles else "当前优势"
    return {
        "认知校准": [
            f"把{style}当工具，不要当身份。工具要接受反证，身份只会保护自尊。",
            cocoon["antidotes"][-1],
        ],
        "行动转化": [
            "每月只保留一个阅读转化任务：一篇文章、一次沟通、一个习惯或一次复盘。",
            "所有读书计划都配一个删除规则；没有退出机制的计划，本质上是焦虑容器。",
        ],
        "表达升级": [
            "减少宏大词汇密度，增加具体场景密度。观点越大，越需要小证据落地。",
            "每篇长评最后加一个反例段，没有反例的判断通常比较爽，但不够硬。",
        ],
    }


def analyze(data: Dict[str, Any], title: str) -> Dict[str, Any]:
    overall = data["stats"]["overall"]
    counts = stat_counts(overall.get("readStat") or [])
    annual_rows = []
    for row in data["stats"]["annual"]:
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

    total_underlines = sum(len(as_list(b.get("underlines"))) for b in book_notes)
    total_reviews = sum(len(as_list(b.get("reviews"))) for b in book_notes)
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
        for item in items:
            item_hits = score_text(item["text"], keywords)
            if item_hits <= 0:
                continue
            hits += item_hits
            if item["kind"] == "personal_review":
                review_hits += item_hits
            else:
                underline_hits += item_hits
            book_hits.add(item["title"])
            score += item_hits * item["weight"]
        if score > 0:
            style_rows.append({
                "name": name,
                "score": score,
                "hits": hits,
                "reviewHits": review_hits,
                "underlineHits": underline_hits,
                "bookCount": len(book_hits),
                "evidence": pick_evidence(items, keywords, style_used_evidence, limit=1),
            })
    style_rows.sort(key=lambda x: x["score"], reverse=True)
    max_style_score = max((s["score"] for s in style_rows), default=1)
    for row in style_rows:
        row["normalized"] = max(1, min(100, round(row["score"] / max_style_score * 100)))
        if row["normalized"] >= 75:
            row["level"] = "强信号"
        elif row["normalized"] >= 45:
            row["level"] = "中信号"
        else:
            row["level"] = "弱信号"

    value_rows = []
    value_used_evidence: set = set()
    for name, keywords in VALUE_SIGNALS.items():
        score = 0
        for item in items:
            score += score_text(item["text"], keywords) * item["weight"]
        if score >= 15:
            value_rows.append({
                "name": name,
                "score": score,
                "evidence": pick_evidence(items, keywords, value_used_evidence, limit=1),
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

    primary_styles = [s["name"] for s in style_rows[:3]]
    primary_themes = [t["name"] for t in theme_rows[:4]]
    primary_values = [v["name"] for v in value_rows[:4]]
    style_names = set(primary_styles)
    theme_names = set(primary_themes)

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

    profile_summary = build_profile_summary(primary_themes, primary_styles, top_cat_share, idea_ratio)
    information_cocoon = build_information_cocoon(categories, theme_rows, top_cat_share, top_theme_share, idea_ratio)
    recommended_books = build_recommended_books(primary_themes, primary_styles, categories, read_titles, information_cocoon)

    portrait = [
        f"你更像一个“{profile_summary['label']}”：阅读不是单纯消遣，更像是在搭建一套解释世界和校准自我的个人系统。高频主题集中在{'、'.join(primary_themes[:3]) or '若干核心议题'}。",
        f"从笔记表达看，你较常使用{'、'.join(primary_styles[:3]) or '复盘和联想'}的方式处理文本：会把书中观点拉回现实案例、个人经验或其他知识来源。",
        "如果只看当前数据，关于人格类型或稳定性格只能初步推测；更可靠的说法是，你在阅读中表现出较强的问题意识、公共议题敏感度和自我修正倾向。",
    ]

    strict_notice = "温馨提示：下面进入审稿人模式。若读到某句觉得刺耳，请先别急着反驳，它可能只是把你笔记里的潜台词念出了声。"
    strict_profile = []
    if completion_rate < 50:
        strict_profile.append(f"完读率约 {completion_rate}%：兴趣启动很快，但收尾纪律偏弱。你不是没耐心，而是容易在一本书完成“解释价值”后提前撤退。")
    else:
        strict_profile.append(f"完读率约 {completion_rate}%：收尾能力不错，但也要警惕为了完成而完成，给无效书及时止损。")
    if idea_ratio >= 35:
        strict_profile.append(f"个人想法占导出内容约 {idea_ratio}%：你有强表达欲，不满足于摘抄。但这也意味着你容易把阅读变成即时评论场，未必总能等材料沉淀。")
    else:
        strict_profile.append(f"个人想法占导出内容约 {idea_ratio}%：摘抄多于自我表达。你可能读得认真，但真正属于你的判断还可以更密。")
    if top_cat_share >= 35:
        strict_profile.append(f"第一分类占比约 {top_cat_share}%：主线清晰，同时有知识偏食风险。你对熟悉议题会越挖越深，对陌生领域可能只是礼貌性路过。")
    else:
        strict_profile.append(f"第一分类占比约 {top_cat_share}%：阅读面较分散，优点是开放，缺点是容易缺少一个可持续累积的硬问题。")
    if {"制度、权力与社会运行", "经济发展与地方现实", "信息环境与公共表达"} & theme_names:
        strict_profile.append("你很容易把文本拉回制度、利益、舆论和现实案例。这是强项，但副作用是审美阅读和纯粹感受可能会被你过早审讯。")
    if "批判辨析" in style_names:
        strict_profile.append("你的批判雷达很灵，看到逻辑缝隙会忍不住上手拆。但批判本身不会自动生成更好的答案，别让锋利感冒充建设性。")
    if "成长导向" in style_names:
        strict_profile.append("你很爱给自己立原则，这很好；问题是原则如果不进入日程表，就只是穿着西装的愿望。")

    blind_spots = [
        "把复杂问题解释得太快：你擅长从机制和利益切入，但要小心把人的偶然、脆弱和荒诞压扁成结构图。",
        "公共议题摄入偏多时，情绪会伪装成理性判断。建议区分“我有证据”和“我只是看不惯”。",
        f"待读完/未完读约 {unfinished_books} 本。阅读野心很足，但如果不定期清理，书架会变成精神待办墓园。",
        "你对成长、自律、行动的语言很熟，下一阶段要少写一点人生方法论，多提交一点可验证结果。",
    ]

    sharper_advice = build_execution_advice(information_cocoon, primary_styles)

    dimension_scores = [
        {"name": "问题意识", "score": min(95, 58 + len(theme_rows) * 5 + (10 if top_theme_share < 25 else 0)), "note": "能从文本里抽出问题，而不是只摘漂亮句子。"},
        {"name": "现实敏感度", "score": min(95, 45 + next((s["score"] for s in style_rows if s["name"] == "现实导向"), 0) // 4), "note": "会把阅读连接到政策、经济、家庭和日常处境。"},
        {"name": "表达密度", "score": min(95, 35 + idea_ratio), "note": "个人想法越多，说明越愿意和作者对话；但密度不等于成熟度。"},
        {"name": "收尾纪律", "score": max(20, min(95, round(completion_rate))), "note": "衡量阅读闭环，不衡量聪明程度。"},
        {"name": "知识均衡", "score": max(20, min(95, 100 - max(top_cat_share - 22, 0) * 2)), "note": "主题越集中，越需要主动补盲区。"},
        {"name": "行动落地", "score": 62 if "成长导向" in style_names else 50, "note": "笔记能看出行动意识，但真实执行只能初步推测。"},
    ]

    suggestions = build_personalized_suggestions(
        primary_themes,
        primary_styles,
        completion_rate,
        idea_ratio,
        information_cocoon,
    )

    return {
        "title": title,
        "generatedAt": data["generatedAt"],
        "profileSummary": profile_summary,
        "basis": {
            "totalReadTime": seconds_text(overall.get("totalReadTime")),
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
            "progressRows": len(data["shelf"]["progress"]),
            "bookInfoRows": len(data["shelf"].get("bookInfo") or []),
            "limited": data["limits"]["maxNoteBooks"] is not None,
        },
        "annual": annual_rows,
        "categories": categories[:10],
        "readLongest": read_longest,
        "topNoteBooks": top_note_books,
        "themes": theme_rows[:8],
        "questions": [t["question"] for t in theme_rows[:6]],
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


def pct_bar(value: float, max_value: float) -> int:
    if max_value <= 0:
        return 0
    return max(4, min(100, round(value / max_value * 100)))


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
    lines.append(f"**画像摘要：{summary['label']}**")
    lines.append("")
    lines.append(summary["tagline"])
    lines.append("")
    lines.append("## 数据基础")
    lines.append("")
    limited = "；本次为抽样导出" if b["limited"] else ""
    lines.append(
        f"本报告基于微信读书个人数据：累计阅读 {b['totalReadTime']}，有效阅读 {b['readDays']} 天，"
        f"读过 {b['booksRead']} 本，读完 {b['booksFinished']} 本，官方笔记口径 {b['notes']} 条。"
        f"书架可见 {b['shelfTotal']} 个条目，其中电子书 {b['shelfBooks']} 本、有声/专辑 {b['albums']} 个、文章收藏入口 {b['mpCount']} 个。"
    )
    lines.append(
        f"已遍历 {b['notebookBooks']} 本有笔记的书，导出 {b['exportedBooks']} 本明细，"
        f"包含 {b['exportedUnderlines']} 条划线和 {b['exportedReviews']} 条个人想法/点评；"
        f"另导出 {b['progressRows']} 条阅读进度和 {b['bookInfoRows']} 条书籍详情{limited}。"
    )
    lines.append("")

    lines.append("## 阅读地图")
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
    lines.append(f"风险等级：{cocoon['level']}，风险分 {cocoon['score']}/100。")
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
        lines.append(f"- {item['name']}：{item['score']}/100。{item['note']}")
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
            f'<div class="score-head"><strong>{html.escape(item["name"])}</strong><span>{item["score"]}</span></div>'
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
        f'<div class="risk-label">风险等级：{html.escape(cocoon["level"])}</div>',
        f'<p>{html.escape(cocoon["summary"])}</p>',
        '</div>',
        '<div class="risk-meter">',
        f'<strong>{cocoon["score"]}</strong><span>/100</span>',
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
    chunk.append(metric("有效阅读天数", b["readDays"]))
    chunk.append(metric("读过/读完", f"{b['booksRead']} / {b['booksFinished']}"))
    chunk.append(metric("官方笔记口径", b["notes"]))
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
    body.append(section("数据基础", "\n".join(chunk), "basis", "featured"))

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

    body.append(section("价值观、焦虑与长期方向", render_value_visual(report["values"]), "values"))

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
    return (
        template
        .replace("{{TITLE}}", html.escape(report["title"]))
        .replace("{{PROFILE_LABEL}}", html.escape(report["profileSummary"]["label"]))
        .replace("{{PROFILE_TAGLINE}}", html.escape(report["profileSummary"]["tagline"]))
        .replace("{{SUBTITLE}}", html.escape(f"生成时间：{report['generatedAt']}。基于全量个人阅读记录和笔记内容。"))
        .replace("{{BODY}}", "\n".join(body))
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deep WeRead profile reports in HTML and Markdown.")
    parser.add_argument("--format", choices=["html", "markdown", "both"], default="both")
    parser.add_argument("--output-dir", default="weread-reports")
    parser.add_argument("--title", default="微信读书深度阅读画像")
    parser.add_argument("--max-note-books", type=int, default=None, help="Limit per-book note fetching for quick tests.")
    parser.add_argument("--skip-progress", action="store_true", help="Skip /book/getprogress calls for shelf books.")
    parser.add_argument("--skip-book-info", action="store_true", help="Skip /book/info calls for shelf and notebook books.")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--retries", type=int, default=3)
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    data = collect_data(args)
    report = analyze(data, args.title)

    skill_dir = Path(__file__).resolve().parents[1]
    template_path = skill_dir / "assets" / "report-template.html"

    written: List[Path] = []
    if args.format in {"markdown", "both"}:
        md_path = out_dir / "weread_deep_report.md"
        md_path.write_text(render_markdown(report), encoding="utf-8")
        written.append(md_path)
    if args.format in {"html", "both"}:
        html_path = out_dir / "weread_deep_report.html"
        html_path.write_text(render_html(report, template_path), encoding="utf-8")
        written.append(html_path)

    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
