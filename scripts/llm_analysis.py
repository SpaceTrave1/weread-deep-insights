"""Shared host/API requests, bounded context planning and evidence provenance."""
from __future__ import annotations

import copy
from pathlib import Path

if __package__:
    from .evidence_bundle import canonical, digest, PROMPT_VERSION, round_robin
    from .llm_validation import RESULT_SCHEMA, validate_result, validate_trace
else:
    from evidence_bundle import canonical, digest, PROMPT_VERSION, round_robin
    from llm_validation import RESULT_SCHEMA, validate_result, validate_trace

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts/reading-analysis-v1.md"


class AnalysisBudgetError(ValueError):
    pass


def make_request(bundle, ids, stage="direct", model="host-declared", provider="host", observations=None, evidence_index=None):
    wanted = set(ids)
    index = evidence_index if evidence_index is not None else {row['evidence_id']: row for row in bundle['evidence']}
    rows = [copy.deepcopy(index[key]) for key in ids if key in index]
    if len(rows) != len(ids):
        raise ValueError("Unknown or duplicate requested evidence")
    context = {"schema_version": "1.0", "prompt_version": PROMPT_VERSION,
               "input_digest": bundle["input_digest"], "provider": provider, "model": model,
               "stage": stage, "evidence": rows, "observations": observations or []}
    if stage != "extract":
        baseline = bundle["baseline_report"]
        context["facts"] = {"basis": {key: baseline["basis"][key] for key in
            ("totalReadTime", "booksRead", "booksFinished", "readDays", "exportedReviews", "exportedUnderlines", "officialStatsAvailable")},
            "categories": baseline["categories"], "annual": baseline["annual"]}
        context["collection_coverage"] = baseline["coverage"]["groups"]
        context["model_selection"] = bundle["selection"]
    return {"stage": stage, "evidence_ids": list(ids), "instructions": PROMPT_PATH.read_text(encoding="utf-8"),
            "context": context, "result_schema": copy.deepcopy(RESULT_SCHEMA)}


def request_chars(request):
    # Character budget is deliberate: stdlib cannot count every provider's tokens.
    return len(request["instructions"]) + len(canonical(request["context"])) + len(canonical(request["result_schema"])) + 512


def plan_requests(bundle, max_input_chars=24000, model="host-declared", provider="host"):
    if max_input_chars < 6000:
        raise AnalysisBudgetError("Input character budget must be at least 6000")
    ids = [row["evidence_id"] for row in bundle["evidence"]]
    index = {row['evidence_id']: row for row in bundle['evidence']}
    if not ids:
        return []
    direct = make_request(bundle, ids, model=model, provider=provider)
    if request_chars(direct) <= max_input_chars:
        return [direct]
    requests = []
    pending = []
    pending_book = None
    rows = sorted(bundle["evidence"], key=lambda row: (row["book_ref"], row["source_ref"], row["fragment_index"]))
    for row in rows:
        next_ids = pending + [row["evidence_id"]]
        candidate = make_request(bundle, next_ids, "extract", model, provider, evidence_index=index)
        if pending and (pending_book != row["book_ref"] or request_chars(candidate) > max_input_chars):
            requests.append(make_request(bundle, pending, "extract", model, provider, evidence_index=index))
            pending = []
        pending.append(row["evidence_id"])
        pending_book = row["book_ref"]
        if request_chars(make_request(bundle, pending, "extract", model, provider, evidence_index=index)) > max_input_chars:
            raise AnalysisBudgetError("A single evidence fragment exceeds input budget; rebuild with smaller fragments")
    if pending:
        requests.append(make_request(bundle, pending, "extract", model, provider, evidence_index=index))
    return requests


def synthesis_request(bundle, partials, max_input_chars=24000, model="host-declared", provider="host"):
    observations = []
    for partial in partials:
        valid = validate_result(partial, bundle, allowed_ids=partial.get('analyzed_evidence_ids', []) if isinstance(partial, dict) else [])
        observations.extend(valid["claims"])
    book_for = {row['evidence_id']: row['book_ref'] for row in bundle['evidence']}
    observations = round_robin(observations, lambda claim: book_for[claim['evidence_ids'][0]])
    selected = []
    ids = []
    index = {row['evidence_id']: row for row in bundle['evidence']}
    for observation in observations:
        candidate_ids = list(dict.fromkeys(ids + observation['evidence_ids'] + observation['counter_evidence_ids']))
        candidate = make_request(bundle, candidate_ids, "synthesize", model, provider, selected + [observation], evidence_index=index)
        if request_chars(candidate) <= max_input_chars:
            selected.append(observation)
            ids = candidate_ids
    if not selected:
        raise AnalysisBudgetError("No evidenced observation fits synthesis budget")
    # Spend remaining space on original notes, including ones not chosen by an
    # extractor. This gives synthesis a chance to find missed counterexamples.
    remaining = round_robin(bundle['evidence'], lambda row: (row['book_ref'], row['kind'], (row['time'] or 'unknown')[:4]))
    for row in remaining:
        if row['evidence_id'] in ids:
            continue
        candidate_ids = ids + [row['evidence_id']]
        candidate = make_request(bundle, candidate_ids, "synthesize", model, provider, selected, evidence_index=index)
        if request_chars(candidate) <= max_input_chars:
            ids = candidate_ids
    return make_request(bundle, ids, "synthesize", model, provider, selected)


def empty_result(bundle, provider="host", model="unspecified", reason="有效正文不足，暂不作结论。"):
    return {"schema_version": "1.0", "prompt_version": PROMPT_VERSION, "input_digest": bundle['input_digest'],
            "provider": provider, "model": model, "status": "abstained", "analyzed_evidence_ids": [],
            "claims": [], "abstentions": [reason]}


def attach_insights(bundle, result=None, failure=None, trace=None):
    report = copy.deepcopy(bundle['baseline_report'])
    valid = validate_result(result, bundle) if result is not None else None
    submitted = set(valid['analyzed_evidence_ids']) if valid else set()
    selected = bundle['evidence']
    # All fragments of a note must be included before counting the note as covered.
    notes = {}
    for row in selected:
        notes.setdefault(row['source_ref'], set()).add(row['evidence_id'])
    covered_notes = sum(ids <= submitted for ids in notes.values())
    report['llmAnalysis'] = {'status': valid['status'] if valid else 'failed',
        'result': valid, 'failure': failure, 'trace': validate_trace(trace or {}),
        'selection': copy.deepcopy(bundle['selection']),
        'coverage': {'selected_fragments': len(selected), 'declared_fragments': len(submitted),
                     'selected_notes': len(notes), 'declared_complete_notes': covered_notes,
                     'available_notes': bundle['selection']['available_notes']},
        'evidence': [copy.deepcopy(row) for row in selected if row['evidence_id'] in submitted],
        'notice': '程序验证了结构、引用和数据绑定；未认证语义正确性。模型覆盖是提交/声明范围，不等于理解质量。'}
    return report
