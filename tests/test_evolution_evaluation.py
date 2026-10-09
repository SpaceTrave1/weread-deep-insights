"""Evaluation gates use invented labels, not real semantic-quality measurements."""
import copy
from test_report import OfflineTest
from scripts.evolution_evaluation import synthetic_cases, summarize


class EvaluationTests(OfflineTest):
    def sheet(self, count=20, supported=True):
        return {'split': 'holdout', 'review_source': 'human-declared', 'cases': [
            {'id': f'fictional-{i}', 'expected_change': True, 'discovery_reviewed': True,
             'predictions': [{'relation': 'revision', 'supported': supported, 'matches_gold': supported}]}
            for i in range(count)]}

    def test_dataset_has_separate_development_and_holdout_and_no_live_source(self):
        cases = synthetic_cases()
        self.assertEqual(len(cases), 60)
        self.assertEqual(len({c['id'] for c in cases}), 60)
        self.assertEqual(sum(c['split'] == 'holdout' for c in cases), 30)
        self.assertTrue(all(c['synthetic'] for c in cases))

    def test_empty_unreviewed_or_small_samples_cannot_pass(self):
        for count in (0, 1, 19): self.assertFalse(summarize(self.sheet(count))['semantic_pass'])
        sheet = self.sheet()
        sheet['cases'][0]['predictions'][0]['supported'] = None
        self.assertFalse(summarize(sheet)['semantic_pass'])

    def test_synthetic_label_gate_math_not_real_model_accuracy(self):
        sheet = self.sheet()
        sheet['cases'][0]['predictions'][0]['supported'] = False
        stats = summarize(sheet)
        self.assertEqual(stats['precision'], 0.95)
        self.assertTrue(stats['semantic_pass'])
        self.assertLess(stats['precision_wilson_95'][0], 0.9)

    def test_self_grading_development_or_unreviewed_discovery_cannot_pass(self):
        for field, value in (('split', 'development'), ('review_source', 'same-model')):
            sheet = self.sheet()
            sheet[field] = value
            self.assertFalse(summarize(sheet)['semantic_pass'])
        sheet = self.sheet()
        sheet['cases'][0]['discovery_reviewed'] = False
        self.assertFalse(summarize(sheet)['semantic_pass'])

    def test_recall_and_no_prediction_denominator_are_explicit(self):
        sheet = self.sheet()
        sheet['cases'][0]['predictions'] = []
        stats = summarize(sheet)
        self.assertEqual(stats['recall_by_case'], 0.95)
        self.assertEqual(stats['predicted_changes'], 19)
        self.assertFalse(stats['semantic_pass'])

    def test_duplicate_cases_and_invalid_labels_rejected(self):
        sheet = self.sheet()
        sheet['cases'].append(copy.deepcopy(sheet['cases'][0]))
        with self.assertRaises(ValueError): summarize(sheet)
        sheet = self.sheet()
        sheet['cases'][0]['predictions'][0]['supported'] = 'yes'
        with self.assertRaises(ValueError): summarize(sheet)
