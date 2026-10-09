"""Versioned local analysis inputs. No credential loading or network access."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import tempfile
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

if __package__:
    from .analysis import analyze, content_items
else:
    from analysis import analyze, content_items

BUNDLE_VERSION = "1.0"
PROMPT_VERSION = "1.0"
MAX_JSON_BYTES = 50 * 1024 * 1024


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    if path.name == ".env" or path.name.startswith(".env."):
        raise ValueError("Credential files are not analysis inputs")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("Analysis JSON exceeds the file size limit")
    def invalid_constant(value):
        raise ValueError("Non-finite JSON number")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid_constant)


def write_json(path: Path, value: Any) -> None:
    if path.name == ".env" or path.name.startswith(".env."):
        raise ValueError("Credential files are not analysis outputs")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def time_value(value: Any) -> Optional[str]:
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        if isinstance(value, str) and value:
            if value.isdigit():
                return datetime.fromtimestamp(int(value), timezone.utc).isoformat()
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return None  # missing timezone cannot establish exact chronology
            return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    return None


def redact_contacts(value: Any) -> Any:
    """Best-effort contact masking, explicitly not complete anonymization."""
    if isinstance(value, str):
        value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", value)
        return re.sub(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)", "[PHONE]", value)
    if isinstance(value, dict):
        return {key: redact_contacts(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_contacts(item) for item in value]
    return value


def round_robin(rows, key):
    strata = defaultdict(list)
    for row in rows:
        strata[key(row)].append(row)
    queues = [deque(strata[label]) for label in sorted(strata)]
    selected = []
    while any(queues):
        for queue in queues:
            if queue:
                selected.append(queue.popleft())
    return selected


def prepare_bundle(data: Dict[str, Any], title: str, max_notes: Optional[int] = None,
                   fragment_chars: int = 2000, redact: bool = True) -> Dict[str, Any]:
    if max_notes is not None and max_notes < 0:
        raise ValueError("max_notes must be nonnegative")
    if fragment_chars < 100:
        raise ValueError("fragment_chars must be at least 100")
    notes = []
    occurrences = defaultdict(int)
    for item in content_items(data):
        # Whitelist fields: never copy raw API responses, errors, tokens or credentials.
        note = {"kind": item["kind"], "book_ref": "book-" + digest(item["bookId"])[:20],
                "title": item["title"], "author": item["author"], "chapter": item["chapter"],
                "text": item["text"], "time": time_value(item["time"])}
        if redact:
            for key in ('title', 'author', 'chapter', 'text'):
                note[key] = redact_contacts(note[key])
        signature = digest(note)
        occurrences[signature] += 1
        note["source_ref"] = "note-" + signature[:24] + f"-{occurrences[signature]}"
        notes.append(note)
    notes.sort(key=lambda row: (row["book_ref"], row["kind"], row["time"] or "", row["source_ref"]))
    ordered = round_robin(notes, lambda row: (row["book_ref"], row["kind"], (row["time"] or "unknown")[:4]))
    selected = ordered if max_notes is None else ordered[:max_notes]
    evidence = []
    for note in selected:
        count = (len(note["text"]) + fragment_chars - 1) // fragment_chars
        for index in range(count):
            row = dict(note)
            row.update(evidence_id=f"{note['source_ref']}-part-{index + 1}",
                       fragment_index=index + 1, fragment_count=count,
                       text=note["text"][index * fragment_chars:(index + 1) * fragment_chars])
            evidence.append(row)
    baseline = json.loads(canonical(analyze(data, title)))
    if redact:
        baseline = redact_contacts(baseline)
    bundle = {"schema_version": BUNDLE_VERSION, "prompt_version": PROMPT_VERSION,
              "baseline_report": baseline, "evidence": evidence,
              "selection": {"policy": "round-robin book/type/year; whole notes before fragmentation",
                            "available_notes": len(notes), "selected_notes": len(selected),
                            "available_books": len({n['book_ref'] for n in notes}),
                            "selected_books": len({n['book_ref'] for n in selected}),
                            "selected_fragments": len(evidence), "max_notes": max_notes},
              "privacy": {"contact_masking": redact,
                          "notice": "Local bundle contains reading content; masking is not full anonymization."}}
    bundle["input_digest"] = digest(bundle)
    return bundle


def validate_bundle(bundle: Any) -> Dict[str, Any]:
    required = {"schema_version", "prompt_version", "baseline_report", "evidence", "selection", "privacy", "input_digest"}
    if not isinstance(bundle, dict) or set(bundle) != required:
        raise ValueError("Invalid analysis bundle fields")
    if bundle["schema_version"] != BUNDLE_VERSION or bundle["prompt_version"] != PROMPT_VERSION:
        raise ValueError("Unsupported analysis bundle version")
    body = {key: value for key, value in bundle.items() if key != "input_digest"}
    if bundle["input_digest"] != digest(body):
        raise ValueError("Analysis bundle digest mismatch")
    if not isinstance(bundle["baseline_report"], dict) or not isinstance(bundle["evidence"], list):
        raise ValueError("Invalid analysis bundle payload")
    baseline = bundle['baseline_report']
    containers = {
        'profileSummary': dict, 'coverage': dict, 'evidenceConditions': dict,
        'basis': dict, 'annual': list, 'categories': list, 'readLongest': list,
        'topNoteBooks': list, 'themes': list, 'questions': list, 'styles': list,
        'values': list, 'people': list, 'portrait': list, 'strictProfile': list,
        'blindSpots': list, 'dimensionScores': list, 'informationCocoon': dict,
        'recommendedBooks': list, 'sharperAdvice': dict, 'suggestions': dict,
    }
    if any(not isinstance(baseline.get(key), kind) for key, kind in containers.items()):
        raise ValueError("Invalid baseline report shape")
    if any(not isinstance(baseline.get(key), str) for key in ('title', 'generatedAt', 'strictNotice')) or 'llmAnalysis' in baseline:
        raise ValueError("Invalid baseline report metadata")
    seen = set()
    sources = defaultdict(list)
    for row in bundle["evidence"]:
        fields = {"kind", "book_ref", "title", "author", "chapter", "text", "time", "source_ref",
                  "evidence_id", "fragment_index", "fragment_count"}
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError("Invalid evidence fields")
        if row["kind"] not in {"personal_review", "underline"}:
            raise ValueError("Invalid evidence kind")
        if any(not isinstance(row[key], str) for key in fields - {"time", "fragment_index", "fragment_count"}):
            raise ValueError("Invalid evidence text fields")
        if not row["text"].strip() or not row["evidence_id"] or row["evidence_id"] in seen:
            raise ValueError("Empty or duplicate evidence")
        if row["time"] is not None and time_value(row["time"]) is None:
            raise ValueError("Invalid evidence timestamp")
        if any(type(row[key]) is not int for key in ("fragment_index", "fragment_count")) or not 1 <= row["fragment_index"] <= row["fragment_count"]:
            raise ValueError("Invalid evidence fragment metadata")
        seen.add(row["evidence_id"])
        if row["evidence_id"] != f"{row['source_ref']}-part-{row['fragment_index']}":
            raise ValueError("Evidence ID does not match fragment identity")
        sources[row["source_ref"]].append(row)
    for source_ref, rows in sources.items():
        first = rows[0]
        if len(rows) != first['fragment_count'] or {r['fragment_index'] for r in rows} != set(range(1, len(rows) + 1)):
            raise ValueError("Evidence note fragments are incomplete")
        fields = ('kind', 'book_ref', 'title', 'author', 'chapter', 'time', 'fragment_count')
        if any(any(row[key] != first[key] for key in fields) for row in rows):
            raise ValueError("Inconsistent note fragment metadata")
    selection = bundle["selection"]
    if not isinstance(selection, dict) or selection.get("selected_fragments") != len(seen):
        raise ValueError("Invalid evidence selection")
    if selection.get("selected_notes") != len({e['source_ref'] for e in bundle['evidence']}):
        raise ValueError("Invalid selected note count")
    for key in ('available_notes', 'selected_notes', 'available_books', 'selected_books', 'selected_fragments'):
        if type(selection.get(key)) is not int or selection[key] < 0:
            raise ValueError("Invalid selection count")
    if selection['selected_notes'] > selection['available_notes'] or selection['selected_books'] > selection['available_books']:
        raise ValueError("Invalid selection denominator")
    if selection['selected_books'] != len({row['book_ref'] for row in bundle['evidence']}):
        raise ValueError("Invalid selected book count")
    if not isinstance(bundle["privacy"], dict):
        raise ValueError("Invalid privacy metadata")
    # Keep a detached baseline, never let a model response mutate official metrics.
    return copy.deepcopy(bundle)
