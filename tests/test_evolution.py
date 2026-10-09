"""Synthetic host-protocol and trajectory regression tests."""
import copy
import tempfile
from pathlib import Path

from test_report import OfflineTest
from test_history import history_data
from scripts.history import HistoryStore
from scripts.evolution_analysis import prepare_extraction, merge_extractions, prepare_comparison, merge_comparisons, validate_response


def extraction_result(request):
    observations = []
    for index, row in enumerate(request['context']['evidence']):
        if row['kind'] == 'personal_review':
            observations.append({'id': f'o-{index}', 'evidence_ids': [row['evidence_id']],
                'question': '如何评价读完一本书？', 'topic': '阅读与理解', 'subject': '完读的价值',
                'stance': '这是虚构的阅读判断', 'conditions': '学习场景', 'reason': '虚构理由',
                'voice': 'own', 'quotes': [{'evidence_id': row['evidence_id'], 'text': row['text'][:30]}],
                'limitations': ['合成样例，语义未评测。']})
    return {'schema_version': 'evolution-result-1.0', 'stage': 'extract', 'input_digest': request['input_digest'],
            'status': 'complete', 'processed_evidence_ids': [e['evidence_id'] for e in request['context']['evidence']],
            'observations': observations, 'abstentions': []}


def comparison_result(request, relation='revision'):
    relations = []
    for candidate in request['context']['candidates']:
        evidence = {e['version_id']: e for e in request['context']['evidence']}
        quotes = [{'evidence_id': evidence[key]['evidence_id'], 'text': evidence[key]['text'][:30]}
                  for key in candidate['version_ids']]
        relations.append({'candidate_id': candidate['id'], 'relation': relation,
            'question': candidate['question'], 'explanation': '虚构的表达修正，仅为协议演示。',
            'comparability': {'same_question': True, 'same_subject': True, 'conditions_compatible': True, 'own_stance': True},
            'quotes': quotes, 'counter_evidence_ids': [], 'limitations': ['合成结果，不表示模型质量。']})
    return {'schema_version': 'evolution-result-1.0', 'stage': 'compare', 'input_digest': request['input_digest'],
            'status': 'complete', 'processed_evidence_ids': [e['evidence_id'] for e in request['context']['evidence']],
            'processed_candidate_ids': [c['id'] for c in request['context']['candidates']],
            'relations': relations, 'abstentions': []}


class EvolutionTests(OfflineTest):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-evolution-', dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.store = HistoryStore(Path(self.temp.name))
        self.addCleanup(self.store.close)
        self.data = history_data()
        self.store.ingest(self.data)
        self.history = self.store.export()

    def pipeline(self, history=None):
        history = history or self.history
        plan = prepare_extraction(history)
        extracted = merge_extractions(history, plan, [extraction_result(r) for r in plan['requests']])
        compared = prepare_comparison(history, extracted)
        return compared

    def test_full_synthetic_pipeline_and_cross_book_trajectory(self):
        plan = self.pipeline()
        report = merge_comparisons(self.history, plan, [comparison_result(r) for r in plan['requests']])
        self.assertEqual(len(report['trajectories']), 1)
        self.assertEqual(report['trajectories'][0]['relation'], 'revision')
        self.assertEqual(report['coverage']['processed_candidates'], 1)
        self.assertFalse(report['semantic_quality_verified'])

    def test_same_book_independent_reviews_are_allowed(self):
        data = history_data()
        data['notebooks']['bookNotes'][0]['reviews'].append({'reviewId': 'fictional-reread', 'content': '虚构重读的新想法', 'createTime': 1764547200})
        with tempfile.TemporaryDirectory(prefix='synthetic-reread-', dir=Path(__file__).parent) as directory:
            with HistoryStore(Path(directory)) as store:
                store.ingest(data)
                history = store.export()
                plan = self.pipeline(history)
                result = merge_comparisons(history, plan, [comparison_result(r) for r in plan['requests']])
                self.assertTrue(any(len({n['book_ref'] for n in t['notes']}) == 1 for t in result['trajectories']))

    def test_only_underlines_cannot_create_own_stance(self):
        plan = prepare_extraction(self.history)
        request = plan['requests'][0]
        response = extraction_result(request)
        underline = next(e for e in request['context']['evidence'] if e['kind'] == 'underline')
        obs = copy.deepcopy(response['observations'][0])
        obs['evidence_ids'] = [underline['evidence_id']]
        obs['quotes'] = [{'evidence_id': underline['evidence_id'], 'text': underline['text']}]
        response['observations'] = [obs]
        with self.assertRaises(ValueError): validate_response(response, request)

    def test_fake_quote_digest_and_unknown_fields_rejected(self):
        request = prepare_extraction(self.history)['requests'][0]
        for bad_kind in ('quote', 'digest', 'extra'):
            result = extraction_result(request)
            if bad_kind == 'quote': result['observations'][0]['quotes'][0]['text'] = '伪造的虚构句子'
            if bad_kind == 'digest': result['input_digest'] = 'wrong'
            if bad_kind == 'extra': result['credential'] = 'never-accepted'
            with self.subTest(bad_kind=bad_kind), self.assertRaises(ValueError): validate_response(result, request)

    def test_partial_extraction_never_becomes_full_coverage(self):
        plan = prepare_extraction(self.history)
        result = extraction_result(plan['requests'][0])
        result['status'] = 'partial'
        result['processed_evidence_ids'] = result['processed_evidence_ids'][:1]
        result['observations'] = []
        merged = merge_extractions(self.history, plan, [result])
        self.assertLess(merged['coverage']['complete_notes'], merged['coverage']['available_notes'])

    def test_long_note_lossless_fragments_and_budget_omissions(self):
        data = history_data()
        data['notebooks']['bookNotes'][0]['reviews'][0]['content'] = '虚构长点评。' * 3000
        with tempfile.TemporaryDirectory(prefix='synthetic-long-', dir=Path(__file__).parent) as directory:
            with HistoryStore(Path(directory)) as store:
                store.ingest(data)
                history = store.export()
                plan = prepare_extraction(history, max_input_chars=9000, max_requests=1)
                self.assertTrue(plan['coverage']['omitted_evidence_ids'])
                self.assertTrue(all(len(str(r)) < 9000 for r in plan['requests']))
                merged = merge_extractions(history, plan, [extraction_result(r) for r in plan['requests']])
                self.assertLess(merged['coverage']['complete_notes'], 5)

    def test_unknown_dates_only_allow_tension(self):
        history = copy.deepcopy(self.history)
        for row in history['notes']: row['effective_at'] = None
        from scripts.evidence_bundle import digest
        history['input_digest'] = digest({k: v for k, v in history.items() if k != 'input_digest'})
        plan = self.pipeline(history)
        with self.assertRaises(ValueError): merge_comparisons(history, plan, [comparison_result(r) for r in plan['requests']])
        result = merge_comparisons(history, plan, [comparison_result(r, 'tension') for r in plan['requests']])
        self.assertEqual(result['trajectories'][0]['relation'], 'tension')

    def test_different_conditions_block_revision(self):
        plan = self.pipeline()
        result = comparison_result(plan['requests'][0])
        result['relations'][0]['comparability']['conditions_compatible'] = False
        with self.assertRaises(ValueError): validate_response(result, plan['requests'][0])
        result['relations'][0]['relation'] = 'tension'
        validate_response(result, plan['requests'][0])

    def test_provisional_identity_cannot_establish_reversal(self):
        history = copy.deepcopy(self.history)
        for row in history['notes']: row['identity'] = 'provisional'
        from scripts.evidence_bundle import digest
        history['input_digest'] = digest({k: v for k, v in history.items() if k != 'input_digest'})
        plan = self.pipeline(history)
        with self.assertRaises(ValueError): merge_comparisons(history, plan, [comparison_result(r, 'reversal') for r in plan['requests']])

    def test_each_side_requires_original_quote(self):
        request = self.pipeline()['requests'][0]
        result = comparison_result(request)
        result['relations'][0]['quotes'] = result['relations'][0]['quotes'][:1]
        with self.assertRaises(ValueError): validate_response(result, request)

    def test_declared_candidate_and_evidence_coverage_checked(self):
        request = self.pipeline()['requests'][0]
        for field in ('processed_candidate_ids', 'processed_evidence_ids'):
            result = comparison_result(request)
            result[field] = []
            with self.subTest(field=field), self.assertRaises(ValueError): validate_response(result, request)

    def test_duplicate_host_results_rejected(self):
        plan = prepare_extraction(self.history)
        result = extraction_result(plan['requests'][0])
        with self.assertRaises(ValueError): merge_extractions(self.history, plan, [result, result])

    def test_history_digest_tampering_rejected(self):
        history = copy.deepcopy(self.history)
        history['notes'][0]['text'] = '虚构被改动'
        with self.assertRaises(ValueError): prepare_extraction(history)

    def test_empty_history_has_no_fake_trajectories(self):
        self.store.clear()
        history = self.store.export()
        extraction = prepare_extraction(history)
        self.assertEqual(extraction['requests'], [])
        merged = merge_extractions(history, extraction, [])
        plan = prepare_comparison(history, merged)
        report = merge_comparisons(history, plan, [])
        self.assertEqual(report['trajectories'], [])
        self.assertEqual(report['status'], 'abstained')

    def test_analysis_is_deterministic_and_read_only(self):
        before = copy.deepcopy(self.history)
        self.assertEqual(self.pipeline(), self.pipeline())
        self.assertEqual(self.history, before)

    def test_edit_versions_do_not_create_two_independent_opinions(self):
        data = history_data()
        data['notebooks']['bookNotes'][1]['reviews'] = []
        with tempfile.TemporaryDirectory(prefix='synthetic-edit-', dir=Path(__file__).parent) as directory:
            with HistoryStore(Path(directory)) as store:
                store.ingest(data)
                data['generatedAt'] = '2026-02-01T00:00:00+08:00'
                data['notebooks']['bookNotes'][0]['reviews'][0]['content'] = '虚构完全相反的编辑内容'
                store.ingest(data)
                self.assertEqual(self.pipeline(store.export())['coverage']['retrieved_candidates'], 0)

    def test_long_fragments_reassemble_exact_original_when_budget_allows(self):
        data = history_data()
        text = '虚构长点评。' * 3000
        data['notebooks']['bookNotes'][0]['reviews'][0]['content'] = text
        with tempfile.TemporaryDirectory(prefix='synthetic-fragments-', dir=Path(__file__).parent) as directory:
            with HistoryStore(Path(directory)) as store:
                store.ingest(data)
                history = store.export()
                plan = prepare_extraction(history, max_requests=100)
                version = next(n['version_id'] for n in history['notes'] if n['text'] == text)
                rows = [r for q in plan['requests'] for r in q['context']['evidence'] if r['version_id'] == version]
                rows.sort(key=lambda r: int(r['evidence_id'].rsplit('-', 1)[1]))
                self.assertEqual(''.join(r['text'] for r in rows), text)

    def test_fully_unprocessed_requests_are_not_marked_empty_success(self):
        plan = self.pipeline()
        report = merge_comparisons(self.history, plan, [])
        self.assertEqual(report['status'], 'not_requested')
        self.assertEqual(report['coverage']['processed_candidates'], 0)
