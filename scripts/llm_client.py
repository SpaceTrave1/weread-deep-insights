"""Explicitly enabled model HTTP adapters. Importing never loads API keys."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

if __package__:
    from .evidence_bundle import canonical, digest, read_json, write_json
    from .llm_analysis import AnalysisBudgetError, request_chars
    from .llm_validation import validate_result
else:
    from evidence_bundle import canonical, digest, read_json, write_json
    from llm_analysis import AnalysisBudgetError, request_chars
    from llm_validation import validate_result


class ModelRequestError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward Authorization or note text to an unapproved destination.
        raise ModelRequestError("Model endpoint redirects are disabled")


def http_post(endpoint, body, headers, timeout):
    request = urllib.request.Request(endpoint, data=canonical(body).encode('utf-8'), headers=headers, method='POST')
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ModelRequestError("Model response exceeds size limit")
    return json.loads(raw.decode('utf-8'))


def validate_endpoint(endpoint):
    parsed = urllib.parse.urlsplit(endpoint)
    local = parsed.hostname in {'localhost', '127.0.0.1', '::1'}
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Endpoint must not contain credentials, query or fragment")
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and local):
        raise ValueError("Model endpoint requires HTTPS, except loopback HTTP")
    return parsed.hostname


class ModelClient:
    def __init__(self, endpoint, model, api_key='', api_style='responses', allow_upload=False,
                 timeout=30, retries=2, max_calls=20, max_input_chars=24000,
                 max_output_tokens=3000, cache_dir=None, json_mode=False, transport=None):
        if not allow_upload:
            raise ValueError("Model upload requires explicit --allow-model-upload")
        self.provider = validate_endpoint(endpoint)
        if not isinstance(model, str) or not model.strip() or len(model) > 200:
            raise ValueError("A model identifier is required")
        if api_style not in {'responses', 'chat'}:
            raise ValueError("Unsupported model API style")
        if any(type(n) is not int or n <= 0 for n in (timeout, retries, max_calls, max_output_tokens)) or max_input_chars < 6000:
            raise ValueError("Invalid model request budget")
        self.endpoint, self.model, self.api_style = endpoint, model, api_style
        self.timeout, self.retries, self.max_calls = timeout, retries, max_calls
        self.max_input_chars, self.max_output_tokens = max_input_chars, max_output_tokens
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.json_mode = json_mode
        self.transport = transport or http_post
        self.headers = {'Content-Type': 'application/json'}
        if api_key:
            self.headers['Authorization'] = 'Bearer ' + api_key
        self.trace = {'calls': 0, 'cache_hits': 0, 'reported_input_tokens': 0,
                      'reported_output_tokens': 0, 'warnings': [], 'stages': []}

    def body(self, request):
        format_spec = {'type': 'json_object'} if self.json_mode else {
            'type': 'json_schema', 'name': 'reading_insights', 'schema': request['result_schema'], 'strict': True}
        if self.api_style == 'responses':
            return {'model': self.model, 'instructions': request['instructions'],
                    'input': canonical(request['context']), 'store': False,
                    'max_output_tokens': self.max_output_tokens, 'text': {'format': format_spec}}
        chat_format = format_spec if self.json_mode else {
            'type': 'json_schema', 'json_schema': {key: value for key, value in format_spec.items() if key != 'type'}}
        return {'model': self.model, 'messages': [
                    {'role': 'system', 'content': request['instructions']},
                    {'role': 'user', 'content': canonical(request['context'])}],
                'store': False, 'max_completion_tokens': self.max_output_tokens,
                'response_format': chat_format}

    def parse(self, response):
        if not isinstance(response, dict):
            raise ModelRequestError("Invalid model response object")
        if self.api_style == 'responses':
            if response.get('status') != 'completed':
                raise ModelRequestError("Model response incomplete")
            outputs = response.get('output')
            if not isinstance(outputs, list) or any(not isinstance(row, dict) for row in outputs):
                raise ModelRequestError("Malformed model output")
            texts = []
            for output in outputs:
                if output.get('type') != 'message':
                    continue
                content = output.get('content')
                if not isinstance(content, list) or any(not isinstance(row, dict) for row in content):
                    raise ModelRequestError("Malformed model message")
                texts.extend(item.get('text', '') for item in content if item.get('type') == 'output_text')
            if any(not isinstance(item, str) for item in texts):
                raise ModelRequestError("Malformed model text")
            text = ''.join(texts)
        else:
            choices = response.get('choices') or []
            if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict) or choices[0].get('finish_reason') != 'stop':
                raise ModelRequestError("Chat response incomplete")
            message = choices[0].get('message') or {}
            if not isinstance(message, dict) or message.get('refusal'):
                raise ModelRequestError("Model refused analysis")
            text = message.get('content')
        if not isinstance(text, str) or not text.strip():
            raise ModelRequestError("Missing model JSON output")
        return json.loads(text)

    def complete(self, request, bundle):
        if request_chars(request) > self.max_input_chars:
            raise AnalysisBudgetError("Input character budget exceeded")
        body = self.body(request)
        if len(canonical(body)) > self.max_input_chars:
            raise AnalysisBudgetError("Serialized model request exceeds input character budget")
        cache_body = json.loads(canonical(body))
        if request['stage'] == 'extract':
            # Only extraction context omits global statistics. Reuse unchanged chunks
            # across new bundles, then rebind and validate their exact source content.
            context = dict(request['context'])
            context.pop('input_digest')
            if self.api_style == 'responses':
                cache_body['input'] = canonical(context)
            else:
                cache_body['messages'][1]['content'] = canonical(context)
        cache_key = digest({'endpoint': self.endpoint, 'style': self.api_style, 'body': cache_body})
        cache_path = self.cache_dir / (cache_key + '.json') if self.cache_dir else None
        if cache_path and cache_path.exists():
            try:
                cached = read_json(cache_path)
                if set(cached) != {'cache_key', 'result'} or cached['cache_key'] != cache_key:
                    raise ValueError("Invalid cache metadata")
                result = cached['result']
                result['input_digest'] = bundle['input_digest']
                result = validate_result(result, bundle, request['evidence_ids'])
                if result['model'] != self.model or result['provider'] != self.provider:
                    raise ValueError("Invalid cached provenance")
                self.trace['cache_hits'] += 1
                return result
            except (ValueError, TypeError, KeyError, OSError):
                self.trace['warnings'].append('缓存未通过校验，重新分析该请求。')
        last_error = 'ModelRequestError'
        for attempt in range(self.retries):
            if self.trace['calls'] >= self.max_calls:
                raise AnalysisBudgetError("Model call budget exhausted")
            self.trace['calls'] += 1
            try:
                response = self.transport(self.endpoint, body, self.headers, self.timeout)
                usage = response.get('usage') or {} if isinstance(response, dict) else {}
                if not isinstance(usage, dict):
                    usage = {}
                for target, source in (('reported_input_tokens', 'input_tokens' if self.api_style == 'responses' else 'prompt_tokens'),
                                       ('reported_output_tokens', 'output_tokens' if self.api_style == 'responses' else 'completion_tokens')):
                    if type(usage.get(source)) is int and usage[source] >= 0:
                        self.trace[target] += usage[source]
                result = validate_result(self.parse(response), bundle, request['evidence_ids'])
                if result['model'] != self.model or result['provider'] != self.provider:
                    raise ModelRequestError("Model provenance mismatch")
                if cache_path:
                    try:
                        write_json(cache_path, {'cache_key': cache_key, 'result': result})
                    except OSError:
                        self.trace['warnings'].append('缓存写入失败，已保留分析结果。')
                self.trace['stages'].append({'stage': request['stage'], 'submitted_fragments': len(request['evidence_ids'])})
                return result
            except urllib.error.HTTPError as exc:
                last_error = f'HTTP{exc.code}'
                if exc.code != 429 and exc.code < 500:
                    break
            except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError, ModelRequestError) as exc:
                last_error = type(exc).__name__  # no response/error body or key in logs
            if attempt + 1 < self.retries and self.trace['calls'] < self.max_calls:
                time.sleep(min(0.5 * (attempt + 1), 2))
        raise ModelRequestError(f"Model analysis failed ({last_error})")
