#!/usr/bin/env python3
"""Prepare host requests or explicitly analyze an existing bundle through HTTP."""
from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path

if __package__:
    from .evidence_bundle import read_json, write_json, validate_bundle, digest
    from .llm_analysis import plan_requests, synthesis_request, empty_result, AnalysisBudgetError
    from .llm_client import ModelClient, ModelRequestError
    from .llm_validation import validate_result
else:
    from evidence_bundle import read_json, write_json, validate_bundle, digest
    from llm_analysis import plan_requests, synthesis_request, empty_result, AnalysisBudgetError
    from llm_client import ModelClient, ModelRequestError
    from llm_validation import validate_result


def add_model_args(parser):
    parser.add_argument('--llm-endpoint', default='https://api.openai.com/v1/responses')
    parser.add_argument('--llm-model')
    parser.add_argument('--llm-api-style', choices=['responses', 'chat'], default='responses')
    parser.add_argument('--allow-model-upload', action='store_true', help='Explicit consent to send prepared content to the configured endpoint.')
    parser.add_argument('--llm-max-input-chars', type=int, default=24000)
    parser.add_argument('--llm-max-output-tokens', type=int, default=3000)
    parser.add_argument('--llm-max-calls', type=int, default=20, help='Counts HTTP attempts, including retries.')
    parser.add_argument('--llm-timeout', type=int, default=30)
    parser.add_argument('--llm-retries', type=int, default=2)
    parser.add_argument('--llm-cache-dir', type=Path, help='Optional private local cache containing model text.')
    parser.add_argument('--llm-json-mode', action='store_true', help='Explicit JSON-mode compatibility option; local validation still applies.')


def client_from_args(args):
    if not args.allow_model_upload:
        raise ValueError("Use --allow-model-upload after reviewing the destination and data")
    # No .env loader: read a dedicated variable only after explicit upload consent.
    client = ModelClient(args.llm_endpoint, args.llm_model,
        api_style=args.llm_api_style, allow_upload=True, timeout=args.llm_timeout,
        retries=args.llm_retries, max_calls=args.llm_max_calls,
        max_input_chars=args.llm_max_input_chars, max_output_tokens=args.llm_max_output_tokens,
        cache_dir=args.llm_cache_dir, json_mode=args.llm_json_mode)
    api_key = os.environ.get('WEREAD_LLM_API_KEY', '')
    if api_key:
        client.headers['Authorization'] = 'Bearer ' + api_key
    return client


def run_analysis(bundle, client):
    requests = plan_requests(bundle, client.max_input_chars, client.model, client.provider)
    if not requests:
        return {'result': empty_result(bundle, client.provider, client.model), 'trace': copy.deepcopy(client.trace)}
    partials = []
    for request in requests:
        try:
            partials.append(client.complete(request, bundle))
        except (AnalysisBudgetError, ModelRequestError):
            client.trace['warnings'].append('部分请求失败或达到调用预算；未完成的片段不计入模型覆盖。')
            if client.trace['calls'] >= client.max_calls:
                break
    if not partials:
        raise ModelRequestError("No validated model result is available")
    if len(requests) == 1 and requests[0]['stage'] == 'direct':
        result = partials[0]
    else:
        try:
            request = synthesis_request(bundle, partials, client.max_input_chars, client.model, client.provider)
            result = client.complete(request, bundle)
        except (AnalysisBudgetError, ModelRequestError):
            client.trace['warnings'].append('跨书综合未完成，仅保留已验证的局部观察。')
            result = empty_result(bundle, client.provider, client.model)
            result['status'] = 'partial'
            result['analyzed_evidence_ids'] = list(dict.fromkeys(key for p in partials for key in p['analyzed_evidence_ids']))
            result['claims'] = [dict(claim, id=f"batch-{index}-{digest(claim['id'])[:24]}") for index, p in enumerate(partials) for claim in p['claims']][:100]
    if len(result['analyzed_evidence_ids']) < len(bundle['evidence']) and result['status'] == 'complete':
        result['status'] = 'partial'
    validate_result(result, bundle)
    client.trace['extraction_declared_fragments'] = len(set(key for p in partials for key in p['analyzed_evidence_ids']))
    client.trace['synthesis_declared_fragments'] = len(result['analyzed_evidence_ids'])
    return {'result': result, 'trace': copy.deepcopy(client.trace)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--mode', choices=['prepare', 'api'], default='prepare')
    parser.add_argument('--partials', type=Path, help='Host-produced JSON array of validated extraction results; prepare synthesis only.')
    add_model_args(parser)
    args = parser.parse_args(argv)
    try:
        bundle = validate_bundle(read_json(args.input))
        if args.mode == 'prepare':
            if args.partials:
                partials = read_json(args.partials)
                if not isinstance(partials, list):
                    raise ValueError("Partial results must be a JSON array")
                requests = [synthesis_request(bundle, partials, args.llm_max_input_chars, args.llm_model or "host-declared")]
            else:
                requests = plan_requests(bundle, args.llm_max_input_chars, args.llm_model or "host-declared")
            write_json(args.output, {'input_digest': bundle['input_digest'], 'requests': requests,
                                     'notice': 'Local reading text; host access follows its own data policy.'})
        else:
            if args.partials:
                raise ValueError("--partials is only supported in prepare mode")
            write_json(args.output, run_analysis(bundle, client_from_args(args)))
    except (ValueError, OSError, KeyError, TypeError, ModelRequestError) as exc:
        parser.exit(2, f"Analysis failed ({type(exc).__name__}); no credentials or response body logged.\n")
    print(args.output.resolve())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
