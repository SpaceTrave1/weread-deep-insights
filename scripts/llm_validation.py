"""Structural and evidence validation. Does not certify semantic correctness."""
from __future__ import annotations

import copy
from typing import Any, Dict

if __package__:
    from .evidence_bundle import PROMPT_VERSION, time_value
else:
    from evidence_bundle import PROMPT_VERSION, time_value

RESULT_VERSION = "1.0"
CATEGORIES = {"theme", "question", "stance", "connection", "change", "portrait", "suggestion"}
RESULT_FIELDS = {"schema_version", "prompt_version", "input_digest", "provider", "model", "status",
                 "analyzed_evidence_ids", "claims", "abstentions"}
CLAIM_FIELDS = {"id", "category", "statement", "scope", "evidence_ids", "quotes", "rationale",
                "counter_evidence_ids", "limitations"}


def object_schema(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


STRING = {"type": "string"}
STRING_ARRAY = {"type": "array", "items": STRING}
RESULT_SCHEMA = object_schema({
    "schema_version": STRING, "prompt_version": STRING, "input_digest": STRING,
    "provider": STRING, "model": STRING, "status": {"type": "string", "enum": ["complete", "partial", "abstained"]},
    "analyzed_evidence_ids": STRING_ARRAY,
    "claims": {"type": "array", "items": object_schema({
        "id": STRING, "category": {"type": "string", "enum": sorted(CATEGORIES)},
        "statement": STRING, "scope": {"type": "string", "enum": ["passage", "sample"]},
        "evidence_ids": STRING_ARRAY,
        "quotes": {"type": "array", "items": object_schema({"evidence_id": STRING, "text": STRING})},
        "rationale": STRING, "counter_evidence_ids": STRING_ARRAY, "limitations": STRING_ARRAY,
    })},
    "abstentions": STRING_ARRAY,
})


class InsightValidationError(ValueError):
    """Messages identify validation rules, never expose user/model content."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InsightValidationError(message)


def strings(value: Any, limit: int = 100) -> bool:
    return isinstance(value, list) and len(value) <= limit and all(isinstance(s, str) and s.strip() and len(s) <= 3000 for s in value)


def validate_trace(trace):
    counts = {'calls', 'cache_hits', 'reported_input_tokens', 'reported_output_tokens',
              'extraction_declared_fragments', 'synthesis_declared_fragments'}
    require(isinstance(trace, dict) and set(trace) <= counts | {'warnings', 'stages'}, "Invalid analysis trace fields")
    require(all(type(trace[key]) is int and trace[key] >= 0 for key in set(trace) & counts), "Invalid trace count")
    require(strings(trace.get('warnings', [])), "Invalid trace warnings")
    stages = trace.get('stages', [])
    require(isinstance(stages, list), "Invalid trace stages")
    for stage in stages:
        require(isinstance(stage, dict) and set(stage) == {'stage', 'submitted_fragments'}, "Invalid stage fields")
        require(stage['stage'] in ('direct', 'extract', 'synthesize') and type(stage['submitted_fragments']) is int
                and stage['submitted_fragments'] >= 0, "Invalid stage values")
    return copy.deepcopy(trace)


def validate_result(result: Any, bundle: Dict[str, Any], allowed_ids=None) -> Dict[str, Any]:
    require(isinstance(result, dict) and set(result) == RESULT_FIELDS, "Unexpected insight fields")
    require(result["schema_version"] == RESULT_VERSION and result["prompt_version"] == PROMPT_VERSION, "Unsupported insight version")
    require(result["input_digest"] == bundle["input_digest"], "Insight input digest mismatch")
    for key in ("provider", "model"):
        require(isinstance(result[key], str) and 0 < len(result[key]) <= 200, "Invalid model provenance")
    require(isinstance(result["status"], str) and result["status"] in {"complete", "partial", "abstained"}, "Invalid insight status")
    evidence = {row["evidence_id"]: row for row in bundle["evidence"]}
    allowed = set(evidence) if allowed_ids is None else set(allowed_ids)
    ids = result["analyzed_evidence_ids"]
    require(strings(ids, len(evidence)) and len(ids) == len(set(ids)), "Invalid analyzed evidence list")
    require(set(ids) <= allowed <= set(evidence), "Unsubmitted evidence in result")
    require(result["status"] != "complete" or set(ids) == allowed, "Incomplete evidence marked complete")
    require(isinstance(result["claims"], list) and len(result["claims"]) <= 100, "Invalid claim list")
    require(strings(result["abstentions"]), "Invalid abstention list")
    require(result["status"] != "abstained" or not result["claims"], "Abstention cannot contain claims")
    require(bool(ids) or not result["claims"], "Claims require analyzed evidence")
    claim_ids = set()
    for claim in result["claims"]:
        require(isinstance(claim, dict) and set(claim) == CLAIM_FIELDS, "Unexpected claim fields")
        require(isinstance(claim["id"], str) and 0 < len(claim["id"]) <= 120 and claim["id"] not in claim_ids, "Duplicate or invalid claim ID")
        claim_ids.add(claim["id"])
        require(isinstance(claim["category"], str) and isinstance(claim["scope"], str)
                and claim["category"] in CATEGORIES and claim["scope"] in {"passage", "sample"}, "Unsupported claim category or scope")
        for key in ("statement", "rationale"):
            require(isinstance(claim[key], str) and 0 < len(claim[key].strip()) <= 3000, "Missing claim explanation")
        require(strings(claim["limitations"]) and bool(claim["limitations"]), "Claim requires explicit limitations")
        support, counter = claim["evidence_ids"], claim["counter_evidence_ids"]
        require(strings(support) and bool(support) and len(support) == len(set(support)), "Invalid supporting references")
        require(strings(counter) and len(counter) == len(set(counter)), "Invalid counter references")
        require(set(support + counter) <= set(ids), "Claim references unprocessed evidence")
        require(not set(support) & set(counter), "Support and counter references overlap")
        rows = [evidence[key] for key in support]
        sources = {row["source_ref"] for row in rows}
        books = {row["book_ref"] for row in rows}
        if claim["scope"] == "sample" or claim['category'] == 'connection':
            require(len(sources) >= 2 and len(books) >= 2, "Sample claim requires independent cross-book evidence")
        if claim["category"] in {"stance", "portrait", "change"}:
            require(all(row["kind"] == "personal_review" for row in rows), "Personal claims require personal reviews")
        if claim["category"] == "portrait":
            reviews = [evidence[key] for key in ids if evidence[key]["kind"] == "personal_review"]
            require(len({row['source_ref'] for row in reviews}) >= 5 and len({row['book_ref'] for row in reviews}) >= 2,
                    "Insufficient portrait review coverage")
            require(len(sources) >= 3 and len(books) >= 2 and claim["scope"] == "sample", "Insufficient portrait support")
        if claim["category"] == "change":
            timestamps = {time_value(row["time"]) for row in rows}
            require(None not in timestamps and len(timestamps) >= 2 and len(sources) >= 2, "Change claim requires distinct dated reviews")
        quotes = claim["quotes"]
        require(isinstance(quotes, list) and 1 <= len(quotes) <= 10, "Claim requires verified quotes")
        for quote in quotes:
            require(isinstance(quote, dict) and set(quote) == {"evidence_id", "text"}, "Invalid quote fields")
            require(isinstance(quote["evidence_id"], str) and quote["evidence_id"] in support + counter, "Quote is not a claim reference")
            text = quote["text"]
            require(isinstance(text, str) and 0 < len(text.strip()) <= 300 and text in evidence[quote["evidence_id"]]["text"], "Quote does not match original text")
    return copy.deepcopy(result)
