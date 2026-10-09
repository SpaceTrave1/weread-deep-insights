"""WeRead collection. Importing this module never reads credentials or calls APIs."""
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional, Tuple
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime
if __package__:
    from .common import API_URL, CN_TZ, PartialFetchError, SKILL_VERSION, UpgradeRequired, as_list, clean_text, date_text, fetch_state, notebook_total, seconds_text, stat_counts, truncate, ts_for_year, valid_records
else:  # direct CLI execution
    from common import API_URL, CN_TZ, PartialFetchError, SKILL_VERSION, UpgradeRequired, as_list, clean_text, date_text, fetch_state, notebook_total, seconds_text, stat_counts, truncate, ts_for_year, valid_records

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
                if "upgrade_info" in data and data["upgrade_info"] is not None:
                    upgrade = data["upgrade_info"]
                    msg = (upgrade.get("message") if isinstance(upgrade, dict) else None) or json.dumps(upgrade, ensure_ascii=False)
                    raise UpgradeRequired(f"WeRead skill upgrade required: {msg}")
                if data.get("errcode"):
                    msg = data.get("errmsg") or data.get("message") or "unknown error"
                    raise RuntimeError(f"API {api_name} failed: {data.get('errcode')} {msg}")
                return data
            except UpgradeRequired:
                raise
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
                last_error = exc
                if attempt + 1 >= self.retries:
                    break
                time.sleep(0.6 * (attempt + 1))
        raise RuntimeError(f"API {api_name} failed after retries: {last_error}") from last_error

def collect_notebooks(client: WeReadClient) -> List[Dict[str, Any]]:
    books: List[Dict[str, Any]] = []
    last_sort: Optional[int] = None
    cursors: set = set()
    seen_books: set = set()
    for _ in range(300):
        payload: Dict[str, Any] = {"count": 100}
        if last_sort is not None:
            payload["lastSort"] = last_sort
        try:
            page = client.fetch("/user/notebooks", **payload)
        except UpgradeRequired:
            raise
        except Exception as exc:
            raise PartialFetchError(books) from exc
        page_books = as_list(page.get("books"))
        for row in page_books:
            key = str(row.get("bookId") or (row.get("book") or {}).get("bookId") or "")
            if not key or key not in seen_books:
                books.append(row)
                if key:
                    seen_books.add(key)
        if int(page.get("hasMore") or 0) != 1:
            return books
        next_sort = page_books[-1].get("sort") if page_books else None
        if next_sort is None or next_sort in cursors:
            raise PartialFetchError(books)
        cursors.add(next_sort)
        last_sort = next_sort
    raise PartialFetchError(books)

def collect_reviews(client: WeReadClient, book_id: str) -> List[Dict[str, Any]]:
    reviews: List[Dict[str, Any]] = []
    synckey = 0
    cursors = {0}
    seen_reviews: set = set()
    for _ in range(100):
        try:
            page = client.fetch("/review/list/mine", bookid=book_id, count=100, synckey=synckey)
        except UpgradeRequired:
            raise
        except Exception as exc:
            raise PartialFetchError(reviews) from exc
        for item in as_list(page.get("reviews")):
            review = item.get("review") or {}
            key = review.get("reviewId") or item.get("reviewId")
            if isinstance(review.get("content"), str) and clean_text(review["content"]) and (not key or key not in seen_reviews):
                # Keep the source identity even when supplied by the outer envelope.
                reviews.append(dict(review, reviewId=key) if key else review)
                if key:
                    seen_reviews.add(key)
        if int(page.get("hasMore") or 0) != 1:
            return reviews
        next_key = page.get("synckey")
        if next_key is None or next_key in cursors:
            raise PartialFetchError(reviews)
        cursors.add(next_key)
        synckey = next_key
    raise PartialFetchError(reviews)

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
        statuses: Dict[str, str] = {}
        errors: Dict[str, str] = {}
        chapters: Dict[str, str] = {}
        try:
            bookmark_data = client.fetch("/book/bookmarklist", bookId=book_id)
            for ch in as_list(bookmark_data.get("chapters")):
                chapters[str(ch.get("chapterUid"))] = clean_text(ch.get("title"))
            for row in as_list(bookmark_data.get("updated")):
                if isinstance(row.get("markText"), str) and clean_text(row["markText"]):
                    underlines.append({
                        "bookmarkId": row.get("bookmarkId"),
                        "text": clean_text(row.get("markText")),
                        "chapterUid": row.get("chapterUid"),
                        "chapterTitle": chapters.get(str(row.get("chapterUid")), ""),
                        "createTime": row.get("createTime"),
                        "updateTime": row.get("updateTime"),
                        "range": row.get("range"),
                    })
            statuses["underlines"] = fetch_state(underlines)
        except UpgradeRequired:
            raise
        except Exception as exc:  # errors are metadata, never note text
            statuses["underlines"] = "failed"
            errors["underlines"] = type(exc).__name__

        try:
            reviews = collect_reviews(client, book_id)
            statuses["reviews"] = fetch_state(reviews)
        except UpgradeRequired:
            raise
        except PartialFetchError as exc:
            reviews = exc.rows
            statuses["reviews"] = "failed"
            errors["reviews"] = "PartialFetchError"
        except Exception as exc:
            reviews = []
            statuses["reviews"] = "failed"
            errors["reviews"] = type(exc).__name__

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
            "fetchStatus": statuses,
            "fetchErrors": errors,
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
                "fetchStatus": fetch_state(row),
            })
        except UpgradeRequired:
            raise
        except Exception as exc:
            progress.append({"bookId": book_id, "fetchStatus": "failed", "error": type(exc).__name__})
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
            info_rows.append({**info, "bookId": book_id, "fetchStatus": fetch_state(info)})
        except UpgradeRequired:
            raise
        except Exception as exc:
            info_rows.append({"bookId": book_id, "fetchStatus": "failed", "error": type(exc).__name__})
        if idx % 25 == 0:
            sys.stderr.write(f"book info fetched: {idx}/{len(book_list)}\n")
    return info_rows

def collect_data(args: argparse.Namespace) -> Dict[str, Any]:
    load_env()
    api_key = os.environ.get("WEREAD_API_KEY")
    if not api_key:
        raise SystemExit("WEREAD_API_KEY is not set. Set it in the environment or a local .env file.")

    client = WeReadClient(api_key, timeout=args.timeout, retries=args.retries)
    collection_status: Dict[str, str] = {}
    def fetch(name: str, endpoint: str, **params: Any) -> Dict[str, Any]:
        try:
            result = client.fetch(endpoint, **params)
            collection_status[name] = fetch_state(result)
            return result
        except UpgradeRequired:
            raise
        except Exception:
            collection_status[name] = "failed"
            return {}

    sys.stderr.write("fetching reading statistics...\n")
    overall = fetch("overall", "/readdata/detail", mode="overall", baseTime=0)
    weekly = fetch("weekly", "/readdata/detail", mode="weekly")
    monthly = fetch("monthly", "/readdata/detail", mode="monthly")

    current_year = datetime.now(CN_TZ).year
    regist_ts = overall.get("registTime")
    start_year = datetime.fromtimestamp(int(regist_ts), CN_TZ).year if regist_ts else current_year
    annual: List[Dict[str, Any]] = []
    for year in range(start_year, current_year + 1):
        name = f"annual:{year}"
        annual.append({"year": year, "data": fetch(name, "/readdata/detail", mode="annually", baseTime=ts_for_year(year)),
                       "fetchStatus": collection_status[name]})
    if not regist_ts:
        collection_status["annualHistory"] = "not_requested"

    sys.stderr.write("fetching shelf...\n")
    shelf = fetch("shelf", "/shelf/sync")
    shelf_books = as_list(shelf.get("books"))
    albums = as_list(shelf.get("albums"))
    progress = [] if args.skip_progress else collect_progress(client, shelf_books)

    sys.stderr.write("fetching notebooks...\n")
    try:
        notebooks = collect_notebooks(client)
        collection_status["notebooks"] = fetch_state(notebooks)
    except UpgradeRequired:
        raise
    except PartialFetchError as exc:
        notebooks = exc.rows
        collection_status["notebooks"] = "failed"
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
        "collectionStatus": collection_status,
    }
