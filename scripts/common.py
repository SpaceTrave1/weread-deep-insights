"""Shared standard-library helpers and request states."""
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional, Tuple
import re
from datetime import datetime, timezone, timedelta

API_URL = "https://i.weread.qq.com/api/agent/gateway"

SKILL_VERSION = "1.0.5"

CN_TZ = timezone(timedelta(hours=8))

class UpgradeRequired(RuntimeError):
    """Gateway upgrades must stop collection, even inside optional fetches."""

class PartialFetchError(RuntimeError):
    def __init__(self, rows: List[Dict[str, Any]]):
        super().__init__("Pagination incomplete")
        self.rows = rows

def fetch_state(rows: Any) -> str:
    return "success" if rows else "empty"

def valid_records(book: Dict[str, Any], field: str) -> List[Dict[str, Any]]:
    status = book.get("fetchStatus") or {}
    if isinstance(status, dict) and status.get(field) in {"empty", "not_requested"}:
        return []
    text_key = "content" if field == "reviews" else "text"
    return [row for row in as_list(book.get(field))
            if isinstance(row, dict) and not row.get("error")
            and isinstance(row.get(text_key), str) and clean_text(row.get(text_key))]

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
        found = re.search(r"-?\d+", counts.replace(",", ""))
        if found:
            result[name] = int(found.group(0))
    return result

def notebook_total(book: Dict[str, Any]) -> int:
    return int(book.get("reviewCount") or 0) + int(book.get("noteCount") or 0) + int(book.get("bookmarkCount") or 0)
