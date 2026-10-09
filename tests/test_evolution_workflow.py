"""Invented feedback, report rendering and offline CLI tests."""
import copy
import tempfile
from pathlib import Path
from unittest.mock import patch

from test_report import OfflineTest
from test_history import history_data
from test_evolution import extraction_result, comparison_result
from scripts.history import HistoryStore
from scripts.evidence_bundle import write_json, read_json
from scripts.evolution_analysis import prepare_extraction, merge_extractions, prepare_comparison, merge_comparisons
from scripts.evolution_workflow import record_feedback, feedback_view, cached_results, cache_results
from scripts.evolution_rendering import render_markdown, render_html, group_questions
from scripts import evolution
from scripts import generate_deep_report


class WorkflowTests(OfflineTest):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-workflow-', dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.store = HistoryStore(self.directory / 'private-history')
        self.addCleanup(self.store.close)
        self.data = history_data()
        self.store.ingest(self.data)
        self.history = self.store.export()
        extracted_plan = prepare_extraction(self.history)
        extracted = merge_extractions(self.history, extracted_plan, [extraction_result(r) for r in extracted_plan['requests']])
        self.plan = prepare_comparison(self.history, extracted)
        self.report = merge_comparisons(self.history, self.plan, [comparison_result(r) for r in self.plan['requests']])

    def feedback(self, status='confirmed', explanation='这是虚构的用户补充。'):
        return {'trajectory_id': self.report['trajectories'][0]['id'], 'status': status, 'explanation': explanation}

    def test_feedback_appends_and_is_not_model_overwritten(self):
        record_feedback(self.store, self.report, self.feedback())
        record_feedback(self.store, self.report, self.feedback('rejected', '虚构条件不同。'))
        row = feedback_view(self.report, self.store.export())[0]
        self.assertEqual(row['feedback']['status'], 'rejected')
        self.assertEqual(len(self.store.feedback_log()), 2)
        self.assertEqual(self.report['trajectories'][0]['confirmation'], 'candidate')

    def test_changed_source_marks_confirmation_stale(self):
        record_feedback(self.store, self.report, self.feedback())
        self.data['generatedAt'] = '2026-02-01T00:00:00+08:00'
        self.data['notebooks']['bookNotes'][0]['reviews'][0]['content'] = '虚构新版本'
        self.store.ingest(self.data)
        row = feedback_view(self.report, self.store.export())[0]
        self.assertTrue(row['needs_review'])
        self.assertEqual(row['feedback']['status'], 'confirmed')

    def test_feedback_dataset_and_status_binding(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-other-', dir=Path(__file__).parent) as directory:
            with HistoryStore(Path(directory)) as other:
                with self.assertRaises(ValueError): record_feedback(other, self.report, self.feedback())
        bad = self.feedback('invalid')
        with self.assertRaises(ValueError): record_feedback(self.store, self.report, bad)

    def test_feedback_cannot_confirm_unsupported_missing_time_change(self):
        report = copy.deepcopy(self.report)
        report['trajectories'][0]['explanation'] = '伪造说明'
        from scripts.evolution_analysis import seal
        report = seal({k: v for k, v in report.items() if k != 'input_digest'})
        with self.assertRaises(ValueError): record_feedback(self.store, report, self.feedback())

    def test_cache_revalidates_and_is_content_bound(self):
        plan = prepare_extraction(self.history)
        results = [extraction_result(r) for r in plan['requests']]
        cache_results(self.store, plan, results)
        self.assertEqual(cached_results(self.store, plan), results)
        self.store.cache_response(plan['requests'][0]['input_digest'], {'bad': True})
        self.assertEqual(cached_results(self.store, plan), [])

    def test_cache_reuse_across_unchanged_snapshot(self):
        plan = prepare_extraction(self.history)
        results = [extraction_result(r) for r in plan['requests']]
        cache_results(self.store, plan, results)
        self.data['generatedAt'] = '2026-02-01T00:00:00+08:00'
        self.store.ingest(self.data)
        next_plan = prepare_extraction(self.store.export())
        self.assertEqual(cached_results(self.store, next_plan), results)

    def test_safe_rendering_full_context_time_and_scope(self):
        md = render_markdown(self.report, self.store.export())
        html = render_html(self.report, self.store.export())
        for text in (md, html):
            self.assertIn('历史版本未知', text)
            self.assertIn('采集', text)
            self.assertIn('反证', text)
            self.assertIn('2024', text)
            self.assertIn('合成科学甲', text)
        self.assertIn('<details', html)

    def test_render_escapes_user_feedback_and_note_markup(self):
        record_feedback(self.store, self.report, self.feedback('clarified', '<script>alert(1)</script> [fake](https://evil.invalid)'))
        html = render_html(self.report, self.store.export())
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        md = render_markdown(self.report, self.store.export())
        self.assertNotIn('[fake](https://evil.invalid)', md)

    def test_offline_cli_roundtrip_and_error_does_not_replace_report(self):
        input_path = self.directory / 'synthetic-input.json'
        write_json(input_path, self.data)
        history_dir = self.directory / 'cli-history'
        out = self.directory / 'plan.json'
        self.assertEqual(evolution.main(['ingest', '--input', str(input_path), '--history-dir', str(history_dir)]), 0)
        self.assertEqual(evolution.main(['prepare', '--history-dir', str(history_dir), '--output', str(out)]), 0)
        plan = read_json(out)
        self.assertEqual(plan['stage'], 'extract')
        self.assertTrue(plan['requests'])

    def test_generator_evolution_uses_mock_collection_and_preserves_old_filename(self):
        with patch.object(generate_deep_report, 'collect_data', return_value=self.data) as mock:
            code = generate_deep_report.main(['--analysis-focus', 'evolution', '--history-dir', str(self.directory / 'generator-history'), '--output-dir', str(self.directory / 'reports')])
        self.assertEqual(code, 0)
        mock.assert_called_once()
        self.assertTrue((self.directory / 'reports' / 'evolution-extract-requests.json').exists())
        self.assertTrue((self.directory / 'reports' / 'weread_deep_report.html').exists())

    def test_generator_offline_render_loads_no_env_or_collection(self):
        path = self.directory / 'report.json'
        write_json(path, self.report)
        with patch.object(generate_deep_report, 'collect_data', side_effect=AssertionError('Collection forbidden')) as mock:
            code = generate_deep_report.main(['--analysis-focus', 'evolution', '--evolution-report', str(path), '--history-dir', str(self.directory / 'private-history'), '--output-dir', str(self.directory / 'offline')])
        self.assertEqual(code, 0)
        mock.assert_not_called()

    def test_invalid_report_is_rejected_before_writing(self):
        path = self.directory / 'bad.json'
        write_json(path, {'schema_version': 'broken'})
        output = self.directory / 'untouched'
        output.mkdir()
        sentinel = output / 'weread_deep_report.html'
        sentinel.write_text('previous', encoding='utf-8')
        code = evolution.main(['render', '--report', str(path), '--history-dir', str(self.directory / 'private-history'), '--output-dir', str(output)])
        self.assertEqual(code, 2)
        self.assertEqual(sentinel.read_text(encoding='utf-8'), 'previous')

    def test_question_timeline_groups_three_notes_and_keeps_intermediate_edges(self):
        data = history_data()
        data['notebooks']['bookNotes'][0]['reviews'].append({'reviewId': 'fictional-middle', 'content': '虚构的中间判断', 'createTime': 1711929600})
        with tempfile.TemporaryDirectory(prefix='synthetic-timeline-', dir=Path(__file__).parent) as directory:
            with HistoryStore(Path(directory)) as store:
                store.ingest(data)
                history = store.export()
                plan = prepare_extraction(history)
                extracted = merge_extractions(history, plan, [extraction_result(r) for r in plan['requests']])
                plan = prepare_comparison(history, extracted)
                report = merge_comparisons(history, plan, [comparison_result(r) for r in plan['requests']])
                groups = group_questions(report, history)
                self.assertEqual(len(groups), 1)
                self.assertEqual(len(groups[0]['notes']), 3)
                self.assertEqual(len(groups[0]['relations']), 3)

    def test_rejected_feedback_is_supplied_to_next_comparison(self):
        record_feedback(self.store, self.report, self.feedback('rejected', '虚构的不同条件。'))
        history = self.store.export()
        plan = prepare_extraction(history)
        extracted = merge_extractions(history, plan, [extraction_result(r) for r in plan['requests']])
        compared = prepare_comparison(history, extracted)
        self.assertIn('虚构的不同条件', str(compared['requests'][0]['context']['feedback']))

    def test_full_cli_merge_index_compare_feedback_and_render(self):
        history_dir = self.directory / 'private-history'
        plan = prepare_extraction(self.history)
        write_json(self.directory / 'extract-plan.json', plan)
        write_json(self.directory / 'extract-results.json', [extraction_result(r) for r in plan['requests']])
        args = ['--history-dir', str(history_dir)]
        self.assertEqual(evolution.main(['merge', *args, '--plan', str(self.directory / 'extract-plan.json'), '--results', str(self.directory / 'extract-results.json'), '--output', str(self.directory / 'extracted.json')]), 0)
        self.assertTrue(self.store.problem_index())
        self.assertEqual(evolution.main(['prepare', *args, '--extractions', str(self.directory / 'extracted.json'), '--output', str(self.directory / 'compare-plan.json')]), 0)
        plan = read_json(self.directory / 'compare-plan.json')
        write_json(self.directory / 'compare-results.json', [comparison_result(r) for r in plan['requests']])
        report_path = self.directory / 'cli-report.json'
        self.assertEqual(evolution.main(['merge', *args, '--plan', str(self.directory / 'compare-plan.json'), '--results', str(self.directory / 'compare-results.json'), '--output', str(report_path)]), 0)
        report = read_json(report_path)
        write_json(self.directory / 'feedback.json', {'trajectory_id': report['trajectories'][0]['id'], 'status': 'clarified', 'explanation': '虚构补充上下文'})
        self.assertEqual(evolution.main(['feedback', *args, '--report', str(report_path), '--input', str(self.directory / 'feedback.json')]), 0)
        self.assertEqual(evolution.main(['render', *args, '--report', str(report_path), '--output-dir', str(self.directory / 'cli-rendered')]), 0)
        self.assertIn('虚构补充上下文', (self.directory / 'cli-rendered' / 'weread_deep_report.html').read_text(encoding='utf-8'))

    def test_fixed_synthetic_demo_has_three_nodes_and_explicit_provenance(self):
        from scripts.create_evolution_demo import create_demo
        paths = create_demo(self.directory / 'fixed-demo')
        report = read_json(self.directory / 'fixed-demo' / 'evolution-report.json')
        self.assertEqual(len(group_questions(report)[0]['notes']), 3)
        self.assertFalse(report['semantic_quality_verified'])
        for path in paths: self.assertIn('合成', path.read_text(encoding='utf-8'))

    def test_clear_wipes_cache_index_feedback_but_keeps_exports_outside_store(self):
        self.store.index_propositions(merge_extractions(self.history, prepare_extraction(self.history), [extraction_result(r) for r in prepare_extraction(self.history)['requests']])['observations'])
        self.store.cache_response('fictional', {'fictional': True})
        record_feedback(self.store, self.report, self.feedback())
        self.store.clear()
        self.assertEqual(self.store.problem_index(), [])
        self.assertIsNone(self.store.get_cached('fictional'))
        self.assertEqual(self.store.feedback_log(), [])

    def test_new_model_explanation_does_not_inherit_old_confirmation(self):
        record_feedback(self.store, self.report, self.feedback())
        results = [comparison_result(r) for r in self.plan['requests']]
        results[0]['relations'][0]['explanation'] = '虚构的新解释，与用户先前确认的解释不同。'
        newer = merge_comparisons(self.history, self.plan, results)
        row = feedback_view(newer, self.store.export())[0]
        self.assertIsNone(row['feedback'])
        self.assertTrue(row['related_feedback'])
        self.assertTrue(row['needs_review'])

    def test_quoted_and_unclear_observations_do_not_enter_personal_problem_index(self):
        plan = prepare_extraction(self.history)
        results = [extraction_result(r) for r in plan['requests']]
        for result in results:
            for row in result['observations']: row['voice'] = 'quoted'
        extracted = merge_extractions(self.history, plan, results)
        self.store.index_propositions(extracted['observations'])
        self.assertEqual(self.store.problem_index(), [])
