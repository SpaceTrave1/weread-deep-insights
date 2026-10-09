"""History contracts, invented notes only; network and credentials forbidden."""
import copy
import tempfile
from pathlib import Path
from unittest.mock import patch

from test_report import OfflineTest, complete_data, FakeClient
from scripts import collection
from scripts.history import HistoryStore, collection_rows


def history_data():
    data = complete_data()
    for b, book in enumerate(data['notebooks']['bookNotes']):
        for n, row in enumerate(book['reviews']):
            row.update(reviewId=f'fictional-review-{b}-{n}', createTime=1704067200 + b * 31536000)
        for n, row in enumerate(book['underlines']):
            # Existing fixture repeats dict objects; give each an independent source identity.
            book['underlines'][n] = dict(row, bookmarkId=f'fictional-mark-{b}-{n}')
    return data


class HistoryTests(OfflineTest):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-history-', dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.store = HistoryStore(Path(self.temp.name))
        self.addCleanup(self.store.close)

    def test_source_collection_preserves_outer_review_identity(self):
        client = FakeClient([{'reviews': [{'reviewId': 'fictional-outer', 'review': {'content': '虚构点评'}}]}])
        self.assertEqual(collection.collect_reviews(client, 'fictional')[0]['reviewId'], 'fictional-outer')

    def test_whitelist_excludes_errors_credentials_and_extra_fields(self):
        data = history_data()
        data['notebooks']['bookNotes'][0]['reviews'].append({'content': '错误占位', 'error': 'failed'})
        data['secret'] = 'excluded-fictional-secret'
        data['notebooks']['bookNotes'][0]['reviews'][0]['token'] = 'excluded-token'
        rows = collection_rows(data)
        self.assertEqual(len(rows), 5)
        self.assertNotIn('excluded', str(rows))
        self.assertNotIn('错误占位', str(rows))

    def test_ingest_does_not_mutate_input(self):
        data = history_data()
        before = copy.deepcopy(data)
        self.store.ingest(data)
        self.assertEqual(data, before)

    def test_repeated_snapshot_keeps_entity_and_version_ids(self):
        data = history_data()
        self.store.ingest(data)
        first = self.store.export()
        data['generatedAt'] = '2026-02-01T00:00:00+08:00'
        self.store.ingest(data)
        second = self.store.export()
        self.assertEqual({n['entity_id'] for n in first['notes']}, {n['entity_id'] for n in second['notes']})
        self.assertEqual({n['version_id'] for n in first['notes']}, {n['version_id'] for n in second['notes']})
        self.assertEqual(len(self.store.versions()), 5)
        self.assertEqual(second['snapshot_count'], 2)

    def test_edit_creates_version_without_new_independent_note(self):
        data = history_data()
        self.store.ingest(data)
        first = self.store.export()['notes']
        data['generatedAt'] = '2026-03-01T00:00:00+08:00'
        data['notebooks']['bookNotes'][0]['reviews'][0]['content'] = '虚构的新表达，不重定年到旧创建日期。'
        self.store.ingest(data)
        notes = self.store.export()['notes']
        edited = next(n for n in notes if n['text'].startswith('虚构的新'))
        old = next(n for n in first if n['entity_id'] == edited['entity_id'])
        self.assertNotEqual(old['version_id'], edited['version_id'])
        self.assertEqual(edited['time_basis'], 'observed_edit')
        self.assertEqual(edited['effective_at'], '2026-02-28T16:00:00+00:00')
        self.assertEqual(len(notes), 5)
        self.assertEqual(len(self.store.versions()), 6)

    def test_metadata_without_content_edit_keeps_version(self):
        data = history_data()
        self.store.ingest(data)
        ids = {n['version_id'] for n in self.store.export()['notes']}
        data['notebooks']['bookNotes'][0]['title'] = '虚构书名更正'
        self.store.ingest(data)
        self.assertEqual(ids, {n['version_id'] for n in self.store.export()['notes']})
        self.assertTrue(any(n['title'] == '虚构书名更正' for n in self.store.export()['notes']))

    def test_missing_on_failed_or_empty_fetch_is_not_deleted(self):
        data = history_data()
        self.store.ingest(data)
        data['generatedAt'] = '2026-04-01T00:00:00+08:00'
        data['notebooks']['bookNotes'][0]['reviews'] = []
        data['notebooks']['bookNotes'][0]['fetchStatus']['reviews'] = 'failed'
        self.store.ingest(data)
        notes = self.store.export()['notes']
        self.assertEqual(len(notes), 5)
        missing = [n for n in notes if n['visibility'] == 'not_observed']
        self.assertEqual(len(missing), 1)
        self.assertNotIn('deleted', str(notes))
        self.assertFalse(self.store.export()['collection_coverage']['notesComplete'])

    def test_bad_snapshot_rolls_back(self):
        self.store.ingest(history_data())
        before = self.store.export()
        bad = history_data()
        bad['generatedAt'] = 'unknown-time'
        with self.assertRaises(ValueError): self.store.ingest(bad)
        self.assertEqual(before, self.store.export())

    def test_missing_source_id_is_provisional_not_auto_merged_after_edit(self):
        data = history_data()
        del data['notebooks']['bookNotes'][0]['reviews'][0]['reviewId']
        self.store.ingest(data)
        data['notebooks']['bookNotes'][0]['reviews'][0]['content'] = '虚构修改，身份未知。'
        self.store.ingest(data)
        provisional = [n for n in self.store.export()['notes'] if n['identity'] == 'provisional']
        self.assertEqual(len(provisional), 2)

    def test_distinct_stores_do_not_share_identity(self):
        self.store.ingest(history_data())
        with tempfile.TemporaryDirectory(prefix='synthetic-other-', dir=Path(__file__).parent) as other:
            with HistoryStore(Path(other)) as store:
                store.ingest(history_data())
                self.assertNotEqual(store.export()['dataset_id'], self.store.export()['dataset_id'])

    def test_time_unknown_and_version_history_are_explicit(self):
        data = history_data()
        data['notebooks']['bookNotes'][0]['reviews'][0]['createTime'] = '2024-01-01'
        self.store.ingest(data)
        notes = self.store.export()['notes']
        self.assertTrue(all(n['historical_version_unknown'] for n in notes))
        self.assertTrue(any(n['effective_at'] is None for n in notes))

    def test_clear_removes_reading_content_and_feedback(self):
        self.store.ingest(history_data())
        self.store.clear()
        self.assertEqual(self.store.export()['notes'], [])
        self.assertEqual(self.store.versions(), [])

    def test_duplicate_source_with_conflicting_content_is_rejected_atomically(self):
        data = history_data()
        review = dict(data['notebooks']['bookNotes'][0]['reviews'][0], content='虚构冲突副本')
        data['notebooks']['bookNotes'][0]['reviews'].append(review)
        with self.assertRaises(ValueError): self.store.ingest(data)
        self.assertEqual(self.store.export()['snapshot_count'], 0)

    def test_open_existing_store_preserves_namespace(self):
        self.store.ingest(history_data())
        namespace = self.store.export()['dataset_id']
        with HistoryStore(Path(self.temp.name)) as reopened:
            self.assertEqual(namespace, reopened.export()['dataset_id'])

    def test_reverting_content_keeps_version_but_records_new_observation_time(self):
        data = history_data()
        original = data['notebooks']['bookNotes'][0]['reviews'][0]['content']
        self.store.ingest(data)
        data['generatedAt'] = '2026-02-01T00:00:00+08:00'
        data['notebooks']['bookNotes'][0]['reviews'][0]['content'] = '虚构第二版'
        self.store.ingest(data)
        data['generatedAt'] = '2026-03-01T00:00:00+08:00'
        data['notebooks']['bookNotes'][0]['reviews'][0]['content'] = original
        self.store.ingest(data)
        row = next(n for n in self.store.export()['notes'] if n['entity_id'] == self.store.versions()[0]['entity_id'])
        edited_rows = [n for n in self.store.export()['notes'] if n['time_basis'] == 'observed_edit']
        self.assertTrue(any(n['effective_at'] == '2026-02-28T16:00:00+00:00' for n in edited_rows))

