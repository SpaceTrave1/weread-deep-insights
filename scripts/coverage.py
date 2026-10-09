"""Request coverage metadata; never contains credentials or note/error text."""
from typing import Any, Dict


STATES = ("success", "empty", "failed", "not_requested", "unknown")


def book_id(row):
    return str(row.get("bookId") or (row.get("book") or {}).get("bookId") or "")


def row_state(row, field=None):
    if row is None:
        return "not_requested"
    status = row.get("fetchStatus", {}) if field else row.get("fetchStatus")
    if field:
        status = status.get(field) if isinstance(status, dict) else None
        if any(r.get("error") for r in row.get(field) or []):
            return "failed"  # legacy placeholder records
    elif row.get("error"):
        return "failed"
    return status if status in STATES else "unknown"


def build_coverage(data: Dict[str, Any], underlines: int, reviews: int) -> Dict[str, Any]:
    groups = {}
    statuses = data.get("collectionStatus", {})

    def group(name, states):
        counts = {state: states.count(state) for state in STATES}
        counts["expected"] = len(states)
        counts["requested"] = counts["success"] + counts["empty"] + counts["failed"]
        groups[name] = counts

    group("汇总与目录", [statuses.get(key, "unknown") for key in ("overall", "weekly", "monthly", "shelf", "notebooks")])
    group("年度统计", [row.get("fetchStatus", "unknown") for row in data["stats"]["annual"]]
          + (["not_requested"] if statuses.get("annualHistory") == "not_requested" else []))
    notebooks = data["notebooks"]["books"]
    # Include missing IDs as uncovered entries, and count a known ID only once.
    expected = list(dict.fromkeys(book_id(row) or f"missing:{idx}" for idx, row in enumerate(notebooks)))
    notes = {book_id(row): row for row in data["notebooks"]["bookNotes"] if book_id(row)}
    for field, label in (("underlines", "划线"), ("reviews", "点评")):
        group(label, [row_state(notes.get(key), field) for key in expected])

    shelf = data["shelf"]
    for field, label, skip, source in (
        ("progress", "进度", "skipProgress", shelf["books"]),
        ("bookInfo", "书籍详情", "skipBookInfo", shelf["books"] + notebooks),
    ):
        keys = list(dict.fromkeys(book_id(row) or f"missing:{idx}" for idx, row in enumerate(source)))
        rows = {book_id(row): row for row in shelf.get(field, []) if book_id(row)}
        group(label, ["not_requested" if data["limits"].get(skip) else row_state(rows.get(key)) for key in keys])

    totals = {state: sum(g[state] for g in groups.values()) for state in STATES}
    expected_underlines = sum(int(b.get("noteCount") or 0) for b in notebooks)
    expected_reviews = sum(int(b.get("reviewCount") or 0) for b in notebooks)
    complete = (statuses.get("notebooks") in {"success", "empty"}
                and all(groups[label]["success"] + groups[label]["empty"] == groups[label]["expected"] for label in ("划线", "点评"))
                and underlines == expected_underlines and reviews == expected_reviews)
    reasons = []
    if data["limits"].get("maxNoteBooks") is not None:
        reasons.append("按笔记数量排序选取，属于定向抽样，不能代表全部阅读")
    if totals["failed"]:
        reasons.append(f"{totals['failed']} 个采集单元失败或分页中断")
    if totals["not_requested"]:
        reasons.append(f"{totals['not_requested']} 个已知采集单元未请求")
    if totals["unknown"]:
        reasons.append("部分数据缺少请求状态，覆盖情况未知")
    if underlines != expected_underlines or reviews != expected_reviews:
        reasons.append("有效文本条数与已获取目录计数不一致")
    scope = "仅分析本次成功获取的可见数据；" + ("；".join(reasons) if reasons else "已知采集单元均完成，仍受接口可见范围限制")
    if statuses.get("notebooks") == "failed":
        scope += "；笔记目录不完整，未发现书籍的数量未知"
    if statuses.get("shelf") == "failed":
        scope += "；书架目录未获取，进度和书籍详情的真实应获取数量未知"
    return {"groups": groups, "totals": totals, "notesComplete": complete,
            "scope": scope, "expectedUnderlines": expected_underlines, "expectedReviews": expected_reviews,
            "exportedUnderlines": underlines, "exportedReviews": reviews,
            "notebookDirectoryStatus": statuses.get("notebooks", "unknown")}


def coverage_lines(coverage):
    lines = [coverage["scope"], "采集单元按端点/书籍/年度计数；成功含非空成功与成功但为空，失败含分页中断，未知不等于成功。"]
    for label, row in coverage["groups"].items():
        lines.append(f"{label}：已知应获取 {row['expected']}，已请求 {row['requested']}，非空成功 {row['success']}，"
                     f"成功但为空 {row['empty']}，失败 {row['failed']}，未请求 {row['not_requested']}，未知 {row['unknown']}。")
    lines.append(f"文本覆盖（已获取目录口径）：划线 {coverage['exportedUnderlines']}/{coverage['expectedUnderlines']}，"
                 f"点评 {coverage['exportedReviews']}/{coverage['expectedReviews']}；不含书签，不保证全账户完整。")
    return lines
