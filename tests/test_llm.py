"""Synthetic evidence and mock model responses only; no live API calls."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.evidence_bundle import prepare_bundle, validate_bundle, digest, read_json, write_json
from scripts.llm_validation import validate_result, InsightValidationError
from scripts.llm_analysis import plan_requests, synthesis_request, make_request, request_chars, attach_insights, AnalysisBudgetError
from scripts.llm_client import ModelClient, ModelRequestError, NoRedirect
from scripts import analyze_bundle
from scripts import generate_deep_report as report
from scripts import evaluate_llm
from scripts import create_synthetic_demo
from test_report import OfflineTest, complete_data


def example_result(bundle, ids=None):
    ids = ids if ids is not None else [row["evidence_id"] for row in bundle["evidence"]]
    row = next((row for row in bundle["evidence"] if row["evidence_id"] in ids), None)
    claims = [] if row is None else [{"id": "synthetic-claim", "category": "theme", "statement": "这条合成文本关注比较方法。",
             "scope": "passage", "evidence_ids": [row["evidence_id"]],
             "quotes": [{"evidence_id": row["evidence_id"], "text": row["text"][:30]}],
             "rationale": "仅从引用片段归纳，无法代表全部阅读。", "counter_evidence_ids": [],
             "limitations": ["合成样例，不能作真实个人结论。"]}]
    return {"schema_version": "1.0", "prompt_version": "1.0", "input_digest": bundle["input_digest"],
            "provider": "synthetic", "model": "mock-model", "status": "complete" if ids else "abstained",
            "analyzed_evidence_ids": ids, "claims": claims, "abstentions": []}


class BundleTests(OfflineTest):
    def test_malformed_baseline_is_rejected_even_with_recomputed_digest(self):
        bundle = prepare_bundle(complete_data(), '合成')
        bundle['baseline_report'] = {}
        bundle['input_digest'] = digest({key: value for key, value in bundle.items() if key != 'input_digest'})
        with self.assertRaises(ValueError): validate_bundle(bundle)

    def test_contact_masking_preserves_hashed_source_identifiers(self):
        with patch('scripts.evidence_bundle.digest', return_value='13800000000' + 'a' * 53):
            bundle = prepare_bundle(complete_data(), '合成')
        self.assertTrue(all(row['book_ref'] == 'book-13800000000aaaaaaaaa' for row in bundle['evidence']))

    def test_missing_fragments_rejected_even_with_recomputed_digest(self):
        bundle = prepare_bundle(long_data(), '合成', fragment_chars=100)
        bundle['evidence'].pop(0)
        bundle['selection']['selected_fragments'] -= 1
        bundle['input_digest'] = digest({key: value for key, value in bundle.items() if key != 'input_digest'})
        with self.assertRaises(ValueError): validate_bundle(bundle)

    def test_whitelist_and_contact_masking(self):
        data = complete_data()
        data["secret_extra"] = "synthetic-secret-excluded"
        data["notebooks"]["bookNotes"][0]["reviews"][0]["content"] = "合成联系 user@example.invalid 13800000000"
        bundle = prepare_bundle(data, "合成")
        text = str(bundle)
        self.assertNotIn("synthetic-secret-excluded", text)
        self.assertNotIn("user@example.invalid", text)
        self.assertNotIn("13800000000", text)
        self.assertIn("[EMAIL]", text)
        self.assertEqual(validate_bundle(bundle), bundle)

    def test_deterministic_and_no_mutation(self):
        data = complete_data()
        before = copy.deepcopy(data)
        bundle = prepare_bundle(data, "合成")
        self.assertEqual(bundle, prepare_bundle(data, "合成"))
        self.assertEqual(data, before)
        self.assertEqual(len({row['evidence_id'] for row in bundle['evidence']}), 5)

    def test_sampling_covers_distinct_books_before_repeating_stratum(self):
        bundle = prepare_bundle(complete_data(), "合成", max_notes=4)
        self.assertEqual(bundle['selection']['available_notes'], 5)
        self.assertEqual(bundle['selection']['selected_notes'], 4)
        self.assertEqual(bundle['selection']['selected_books'], 2)

    def test_long_notes_are_losslessly_fragmented(self):
        data = complete_data()
        text = "合成片段" * 100
        data['notebooks']['bookNotes'][0]['reviews'][0]['content'] = text
        bundle = prepare_bundle(data, '合成', fragment_chars=100)
        parts = [row for row in bundle['evidence'] if row['kind'] == 'personal_review' and row['title'] == '合成科学甲']
        self.assertEqual(''.join(row['text'] for row in parts), text)
        self.assertEqual(len({row['source_ref'] for row in parts}), 1)

    def test_digest_tampering_and_extra_fields_rejected(self):
        bundle = prepare_bundle(complete_data(), '合成')
        bundle['evidence'][0]['text'] = '合成被改动'
        with self.assertRaises(ValueError):
            validate_bundle(bundle)
        bundle = prepare_bundle(complete_data(), '合成')
        bundle['api_key'] = 'synthetic-not-real'
        with self.assertRaises(ValueError):
            validate_bundle(bundle)

    def test_empty_bundle_and_local_roundtrip(self):
        bundle = prepare_bundle(complete_data(), '合成', max_notes=0)
        self.assertEqual(bundle['evidence'], [])
        self.assertEqual(validate_result(example_result(bundle), bundle)['status'], 'abstained')
        with tempfile.TemporaryDirectory(prefix='synthetic-', dir=Path(__file__).parent) as directory:
            path = Path(directory) / 'bundle.json'
            write_json(path, bundle)
            self.assertEqual(read_json(path), bundle)
            with self.assertRaises(ValueError):
                read_json(Path(directory) / '.env')


class ValidationTests(OfflineTest):
    def setUp(self):
        super().setUp()
        self.bundle = prepare_bundle(complete_data(), '合成')
        self.result = example_result(self.bundle)

    def test_valid_result_is_detached(self):
        output = validate_result(self.result, self.bundle)
        self.assertEqual(output, self.result)
        output['claims'][0]['statement'] = '合成修改'
        self.assertNotEqual(output, self.result)

    def test_fabricated_quote_and_reference_are_rejected(self):
        for field in ('quote', 'reference', 'digest', 'statistic'):
            with self.subTest(field=field):
                result = copy.deepcopy(self.result)
                if field == 'quote': result['claims'][0]['quotes'][0]['text'] = '不存在的合成原文'
                if field == 'reference': result['claims'][0]['evidence_ids'] = ['fake-evidence']
                if field == 'digest': result['input_digest'] = 'fake-digest'
                if field == 'statistic': result['basis'] = {'booksRead': 999}
                with self.assertRaises(InsightValidationError):
                    validate_result(result, self.bundle)

    def test_partial_cannot_claim_complete_or_cite_unsubmitted_text(self):
        ids = self.result['analyzed_evidence_ids'][:1]
        result = example_result(self.bundle, ids)
        with self.assertRaises(InsightValidationError): validate_result(result, self.bundle)
        result['status'] = 'partial'
        self.assertEqual(validate_result(result, self.bundle)['status'], 'partial')
        with self.assertRaises(InsightValidationError): validate_result(self.result, self.bundle, allowed_ids=ids)

    def test_underlines_cannot_prove_personal_stance(self):
        row = next(row for row in self.bundle['evidence'] if row['kind'] == 'underline')
        result = example_result(self.bundle, [row['evidence_id']])
        result['status'] = 'partial'
        result['claims'][0]['category'] = 'stance'
        with self.assertRaises(InsightValidationError): validate_result(result, self.bundle)

    def test_single_book_or_fragment_does_not_support_global_portrait(self):
        result = copy.deepcopy(self.result)
        for category, scope in [('portrait', 'sample'), ('theme', 'sample'), ('theme', 'account')]:
            with self.subTest(category=category, scope=scope):
                result['claims'][0].update(category=category, scope=scope)
                with self.assertRaises(InsightValidationError): validate_result(result, self.bundle)

    def test_cross_book_connection_requires_two_books_even_for_passage_scope(self):
        self.result['claims'][0]['category'] = 'connection'
        with self.assertRaises(InsightValidationError): validate_result(self.result, self.bundle)
        ids = self.result['analyzed_evidence_ids']
        self.result['claims'][0]['evidence_ids'] = ids
        self.assertEqual(validate_result(self.result, self.bundle)['claims'][0]['category'], 'connection')

    def test_undated_reviews_cannot_show_time_change(self):
        result = copy.deepcopy(self.result)
        row = next(row for row in self.bundle['evidence'] if row['kind'] == 'personal_review')
        result['claims'][0].update(category='change', evidence_ids=[row['evidence_id']],
                                   quotes=[{'evidence_id': row['evidence_id'], 'text': row['text'][:20]}])
        with self.assertRaises(InsightValidationError): validate_result(result, self.bundle)

    def test_dated_expression_change_is_supported_without_fixed_theme_taxonomy(self):
        dataset = read_json(evaluate_llm.CASES_PATH)
        case = next(c for c in dataset['cases'] if c['id'] == 'dated-expression-change')
        bundle = prepare_bundle(evaluate_llm.case_data(case), '合成')
        result = example_result(bundle)
        claim = result['claims'][0]
        ids = result['analyzed_evidence_ids']
        claim.update(category='change', evidence_ids=ids, statement='两条有日期点评对停读的表述发生变化。')
        self.assertEqual(validate_result(result, bundle)['claims'][0]['category'], 'change')

    def test_trace_injection_and_duplicate_claims_are_rejected(self):
        with self.assertRaises(InsightValidationError):
            attach_insights(self.bundle, self.result, trace={'calls': '<script>synthetic</script>'})
        self.result['claims'] *= 2
        with self.assertRaises(InsightValidationError): validate_result(self.result, self.bundle)


def mock_transport(bundle, style='responses'):
    def call(endpoint, body, headers, timeout):
        context = json.loads(body['input'] if style == 'responses' else body['messages'][1]['content'])
        ids = [row['evidence_id'] for row in context['evidence']]
        result = example_result(bundle, ids)
        result.update(input_digest=context['input_digest'], model=context['model'], provider=context['provider'])
        if context['stage'] == 'extract':
            result['status'] = 'partial'
        if style == 'responses':
            return {'status': 'completed', 'usage': {'input_tokens': 100, 'output_tokens': 40},
                    'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(result)}]}]}
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(result)}}],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 40}}
    return call


def synthetic_client(bundle, **options):
    config = dict(endpoint='https://model.example.invalid/v1/responses', model='mock-model',
                  api_key='synthetic-token', allow_upload=True, transport=mock_transport(bundle), retries=1)
    config.update(options)
    return ModelClient(**config)


def long_data():
    data = complete_data()
    for index, row in enumerate(data['notebooks']['bookNotes']):
        row['reviews'] = [{'content': f'合成{i}：不赞同这个比喻，需要反例。' * 70} for i in range(6)]
        data['notebooks']['books'][index]['reviewCount'] = 6
    return data


class PipelineTests(OfflineTest):
    def test_direct_prompt_keeps_raw_api_and_rule_portrait_out(self):
        bundle = prepare_bundle(complete_data(), '合成')
        request = plan_requests(bundle)[0]
        self.assertEqual(request['stage'], 'direct')
        self.assertNotIn('baseline_report', request['context'])
        self.assertNotIn('portrait', request['context']['facts'])
        self.assertIn('UNTRUSTED DATA', request['instructions'])

    def test_chunk_plan_covers_every_fragment_with_bounded_requests(self):
        bundle = prepare_bundle(long_data(), '合成', fragment_chars=1000)
        requests = plan_requests(bundle, max_input_chars=9000)
        self.assertGreater(len(requests), 1)
        ids = [key for request in requests for key in request['evidence_ids']]
        self.assertEqual(set(ids), {row['evidence_id'] for row in bundle['evidence']})
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(request_chars(r) <= 9000 for r in requests))

    def test_synthesis_uses_original_evidence_and_exposes_partial_scope(self):
        bundle = prepare_bundle(long_data(), '合成', fragment_chars=1000)
        partials = []
        for request in plan_requests(bundle, 9000)[:2]:
            result = example_result(bundle, request['evidence_ids'])
            result['status'] = 'partial'
            partials.append(result)
        request = synthesis_request(bundle, partials, 9000)
        self.assertTrue(request['context']['observations'])
        self.assertTrue(request['context']['evidence'])
        self.assertLess(len(request['evidence_ids']), len(bundle['evidence']))

    def test_too_small_budget_and_oversized_fragment_fail_clearly(self):
        bundle = prepare_bundle(long_data(), '合成', fragment_chars=5000)
        with self.assertRaises(AnalysisBudgetError): plan_requests(bundle, 100)
        with self.assertRaises(AnalysisBudgetError): plan_requests(bundle, 6000)

    def test_enhanced_report_does_not_modify_statistics_and_escapes_model_text(self):
        bundle = prepare_bundle(complete_data(), '合成')
        result = example_result(bundle)
        result['claims'][0]['statement'] = '<script>synthetic</script> [link](https://example.invalid)'
        enhanced = attach_insights(bundle, result)
        self.assertEqual(enhanced['basis'], bundle['baseline_report']['basis'])
        template = Path(__file__).resolve().parents[1] / 'assets/report-template.html'
        rendered = report.render_html(enhanced, template)
        self.assertIn('大模型语义分析', rendered)
        self.assertNotIn('<script>synthetic', rendered)
        self.assertIn('与 API 采集覆盖分别计算', rendered)
        self.assertIn(r'\[link\]', report.render_markdown(enhanced))

    def test_fragments_do_not_inflate_note_coverage(self):
        bundle = prepare_bundle(long_data(), '合成', fragment_chars=100)
        result = example_result(bundle, [bundle['evidence'][0]['evidence_id']])
        result['status'] = 'partial'
        analysis = attach_insights(bundle, result)['llmAnalysis']
        self.assertEqual(analysis['coverage']['declared_fragments'], 1)
        self.assertEqual(analysis['coverage']['declared_complete_notes'], 0)


class ClientTests(OfflineTest):
    def test_malformed_protocol_shapes_do_not_escape_sanitized_errors(self):
        bundle = prepare_bundle(complete_data(), '合成')
        for response in ({'status': 'completed', 'output': ['fake']},
                         {'status': 'completed', 'output': [{'type': 'message', 'content': ['fake']}]},
                         {'status': 'completed', 'output': [], 'usage': ['fake']}):
            with self.subTest(response=response):
                client = synthetic_client(bundle, transport=lambda *args: response)
                request = plan_requests(bundle, model=client.model, provider=client.provider)[0]
                with self.assertRaises(ModelRequestError): client.complete(request, bundle)

    def test_json_mode_keeps_local_validation_enabled(self):
        bundle = prepare_bundle(complete_data(), '合成')
        client = synthetic_client(bundle, json_mode=True)
        request = plan_requests(bundle, model=client.model, provider=client.provider)[0]
        self.assertEqual(client.body(request)['text']['format'], {'type': 'json_object'})
        self.assertEqual(client.complete(request, bundle)['status'], 'complete')
    def test_upload_opt_in_and_endpoint_rules(self):
        with self.assertRaises(ValueError):
            ModelClient('https://model.example.invalid', 'mock', allow_upload=False)
        for endpoint in ('http://example.invalid', 'https://user:pass@example.invalid', 'https://example.invalid/?key=synthetic'):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                ModelClient(endpoint, 'mock', allow_upload=True)
        self.assertEqual(ModelClient('http://localhost:1234/v1/chat/completions', 'mock', allow_upload=True).provider, 'localhost')

    def test_responses_and_chat_request_protocols(self):
        bundle = prepare_bundle(complete_data(), '合成')
        for style in ('responses', 'chat'):
            with self.subTest(style=style):
                client = synthetic_client(bundle, api_style=style, transport=mock_transport(bundle, style))
                request = plan_requests(bundle, model=client.model, provider=client.provider)[0]
                self.assertFalse(client.body(request)['store'])
                output = analyze_bundle.run_analysis(bundle, client)
                self.assertEqual(output['result']['status'], 'complete')
                self.assertEqual(output['trace']['reported_output_tokens'], 40)
                self.assertNotIn('synthetic-token', str(output))

    def test_retry_budget_counts_attempts_and_errors_do_not_leak(self):
        bundle = prepare_bundle(complete_data(), '合成')
        with patch('scripts.llm_client.time.sleep'):
            client = synthetic_client(bundle, retries=4, max_calls=2,
                transport=lambda *args: (_ for _ in ()).throw(TimeoutError('synthetic-secret-must-not-leak')))
            request = plan_requests(bundle, model=client.model, provider=client.provider)[0]
            with self.assertRaises(AnalysisBudgetError) as error: client.complete(request, bundle)
        self.assertEqual(client.trace['calls'], 2)
        self.assertNotIn('synthetic-secret', str(error.exception))

    def test_truncated_and_fabricated_model_outputs_are_rejected(self):
        bundle = prepare_bundle(complete_data(), '合成')
        for response in ({'status': 'incomplete', 'output': []},
                         {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': '{}'}]}]}):
            with self.subTest(response=response):
                client = synthetic_client(bundle, transport=lambda *args: response)
                request = plan_requests(bundle, model=client.model, provider=client.provider)[0]
                with self.assertRaises(ModelRequestError): client.complete(request, bundle)

    def test_cache_reuse_and_corrupted_cache_revalidation(self):
        bundle = prepare_bundle(complete_data(), '合成')
        with tempfile.TemporaryDirectory(prefix='synthetic-', dir=Path(__file__).parent) as directory:
            client = synthetic_client(bundle, cache_dir=directory)
            request = plan_requests(bundle, model=client.model, provider=client.provider)[0]
            first = client.complete(request, bundle)
            client.transport = lambda *args: self.fail('Should use validated cache')
            self.assertEqual(client.complete(request, bundle), first)
            self.assertEqual(client.trace['cache_hits'], 1)
            path = next(Path(directory).glob('*.json'))
            write_json(path, {'cache_key': 'synthetic-corrupt', 'result': {}})
            client.transport = mock_transport(bundle)
            client.complete(request, bundle)
            self.assertEqual(client.trace['calls'], 2)

    def test_incremental_extraction_cache_rebinds_only_identical_context(self):
        first = prepare_bundle(long_data(), '合成', fragment_chars=1000)
        data = long_data()
        data['stats']['overall']['totalReadTime'] += 3600
        second = prepare_bundle(data, '合成', fragment_chars=1000)
        self.assertNotEqual(first['input_digest'], second['input_digest'])
        with tempfile.TemporaryDirectory(prefix='synthetic-', dir=Path(__file__).parent) as directory:
            client = synthetic_client(first, cache_dir=directory, max_input_chars=9000)
            request = plan_requests(first, 9000, client.model, client.provider)[0]
            client.complete(request, first)
            client.transport = lambda *args: self.fail('Unchanged extraction must use cache')
            request = plan_requests(second, 9000, client.model, client.provider)[0]
            result = client.complete(request, second)
            self.assertEqual(result['input_digest'], second['input_digest'])
            self.assertEqual(client.trace['cache_hits'], 1)

    def test_chunk_budget_failure_retains_only_local_observations(self):
        bundle = prepare_bundle(long_data(), '合成', fragment_chars=1000)
        client = synthetic_client(bundle, max_calls=1, max_input_chars=9000)
        transport = client.transport
        def long_claim_id(*args):
            response = transport(*args)
            content = response['output'][0]['content'][0]
            result = json.loads(content['text'])
            result['claims'][0]['id'] = 'x' * 120
            content['text'] = json.dumps(result)
            return response
        client.transport = long_claim_id
        output = analyze_bundle.run_analysis(bundle, client)
        self.assertEqual(output['result']['status'], 'partial')
        self.assertEqual(output['trace']['calls'], 1)
        self.assertLess(len(output['result']['analyzed_evidence_ids']), len(bundle['evidence']))
        self.assertTrue(output['trace']['warnings'])
        self.assertLessEqual(len(output['result']['claims'][0]['id']), 120)

    def test_redirects_do_not_forward_data_or_authorization(self):
        with self.assertRaises(ModelRequestError):
            NoRedirect().redirect_request(None, None, 302, 'fake', {}, 'https://other.example.invalid')


class EnhancedCLITests(OfflineTest):
    def test_corrupt_nested_baseline_does_not_write_either_report(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-', dir=Path(__file__).parent) as directory:
            root = Path(directory)
            bundle = prepare_bundle(complete_data(), '合成')
            bundle['baseline_report']['profileSummary'] = {}
            bundle['input_digest'] = digest({key: value for key, value in bundle.items() if key != 'input_digest'})
            write_json(root / 'bundle.json', bundle)
            self.assertEqual(report.main(['--analysis-input', str(root / 'bundle.json'), '--output-dir', str(root)]), 2)
            self.assertFalse((root / 'weread_deep_report.md').exists())
            self.assertFalse((root / 'weread_deep_report.html').exists())

    def test_api_cli_roundtrip_uses_mock_transport_without_key_reading(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-', dir=Path(__file__).parent) as directory:
            root = Path(directory)
            bundle = prepare_bundle(complete_data(), '合成')
            write_json(root / 'bundle.json', bundle)
            with patch.object(analyze_bundle, 'client_from_args', return_value=synthetic_client(bundle)):
                self.assertEqual(analyze_bundle.main(['--input', str(root / 'bundle.json'), '--output', str(root / 'result.json'), '--mode', 'api']), 0)
            output = read_json(root / 'result.json')
            self.assertEqual(output['trace']['calls'], 1)
            self.assertEqual(report.main(['--analysis-input', str(root / 'bundle.json'), '--analysis-result', str(root / 'result.json'), '--output-dir', str(root)]), 0)

    def test_api_failure_report_retains_attempt_counts(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-', dir=Path(__file__).parent) as directory:
            root = Path(directory)
            bundle = prepare_bundle(complete_data(), '合成')
            write_json(root / 'bundle.json', bundle)
            client = synthetic_client(bundle, transport=lambda *args: {'status': 'incomplete'})
            with patch.object(report, 'client_from_args', return_value=client):
                self.assertEqual(report.main(['--analysis-input', str(root / 'bundle.json'), '--analysis-mode', 'llm',
                    '--allow-model-upload', '--llm-model', 'mock-model', '--output-dir', str(root)]), 2)
            self.assertIn('请求尝试 1', (root / 'weread_deep_report.md').read_text(encoding='utf-8'))
    def test_export_and_offline_host_roundtrip(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-', dir=Path(__file__).parent) as directory:
            root = Path(directory)
            path = root / 'bundle.json'
            with patch.object(report, 'collect_data', return_value=complete_data()):
                self.assertEqual(report.main(['--output-dir', str(root), '--export-analysis-bundle', str(path)]), 0)
            bundle = validate_bundle(read_json(path))
            result_path = root / 'result.json'
            write_json(result_path, example_result(bundle))
            with patch.object(report, 'collect_data', side_effect=AssertionError('Must not refetch')):
                self.assertEqual(report.main(['--analysis-input', str(path), '--analysis-result', str(result_path), '--output-dir', str(root)]), 0)
            self.assertIn('大模型语义分析', (root / 'weread_deep_report.md').read_text(encoding='utf-8'))

    def test_invalid_model_import_writes_fallback_and_returns_nonzero(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-', dir=Path(__file__).parent) as directory:
            root = Path(directory)
            write_json(root / 'bundle.json', prepare_bundle(complete_data(), '合成'))
            write_json(root / 'result.json', {'fake': 'synthetic-secret'})
            self.assertEqual(report.main(['--analysis-input', str(root / 'bundle.json'), '--analysis-result', str(root / 'result.json'), '--output-dir', str(root)]), 2)
            text = (root / 'weread_deep_report.md').read_text(encoding='utf-8')
            self.assertIn('增强分析未完成', text)
            self.assertNotIn('synthetic-secret', text)

    def test_prepare_mode_is_offline_and_uses_no_credentials(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-', dir=Path(__file__).parent) as directory:
            root = Path(directory)
            write_json(root / 'bundle.json', prepare_bundle(complete_data(), '合成'))
            with patch.object(analyze_bundle, 'client_from_args', side_effect=AssertionError('No API')):
                self.assertEqual(analyze_bundle.main(['--input', str(root / 'bundle.json'), '--output', str(root / 'requests.json')]), 0)
            self.assertTrue(read_json(root / 'requests.json')['requests'])

    def test_missing_opt_in_fails_before_fetch_or_key_loading(self):
        with self.assertRaises(SystemExit):
            report.parse_args(['--analysis-mode', 'llm', '--llm-model', 'mock'])
        args = report.parse_args([])
        with patch.object(analyze_bundle.os.environ, 'get', side_effect=AssertionError('No key access')):
            with self.assertRaises(ValueError): analyze_bundle.client_from_args(args)

    def test_all_new_direct_and_module_help_entry_points(self):
        root = Path(__file__).resolve().parents[1]
        for command in ([sys.executable, str(root / 'scripts/analyze_bundle.py'), '--help'],
                        [sys.executable, '-m', 'scripts.analyze_bundle', '--help']):
            output = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=20)
            self.assertEqual(output.returncode, 0, output.stderr)
            self.assertIn('--allow-model-upload', output.stdout)


class EvaluationTests(OfflineTest):
    def test_authored_synthetic_demo_renders_verified_evidence(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-', dir=Path(__file__).parent) as directory:
            self.assertEqual(create_synthetic_demo.main(['--output-dir', directory]), 0)
            root = Path(directory)
            bundle = validate_bundle(read_json(root / 'bundle.json'))
            result = validate_result(read_json(root / 'insights.json'), bundle)
            self.assertEqual(result['provider'], 'synthetic-demo')
            self.assertIn('园艺观察与对照试验', (root / 'weread_deep_report.html').read_text(encoding='utf-8'))

    def test_prepared_synthetic_holdout_has_no_grade_or_rubric_leak(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-', dir=Path(__file__).parent) as directory:
            root = Path(directory)
            with patch.object(evaluate_llm, 'client_from_args', side_effect=AssertionError('Offline prepare')):
                self.assertEqual(evaluate_llm.main(['--mode', 'prepare', '--split', 'holdout', '--output-dir', str(root)]), 0)
            summary = read_json(root / 'evaluation.json')
            self.assertEqual(len(summary['cases']), 4)
            self.assertTrue(all(case['semantic_support'] is None for case in summary['cases']))
            request = read_json(root / 'multilingual-notes/requests.json')
            self.assertNotIn('manual_rubric', str(request))
            self.assertNotIn('不能把语言选择推断为身份', str(request))

    def test_arbitrary_theme_names_pass_evidence_contract(self):
        case = read_json(evaluate_llm.CASES_PATH)['cases'][0]
        bundle = prepare_bundle(evaluate_llm.case_data(case), '合成')
        result = example_result(bundle)
        result['claims'][0].update(statement='园艺观察与对照试验', scope='sample',
                                   evidence_ids=result['analyzed_evidence_ids'])
        self.assertEqual(validate_result(result, bundle)['claims'][0]['statement'], '园艺观察与对照试验')


if __name__ == '__main__':
    unittest.main()
