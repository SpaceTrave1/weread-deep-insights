"""Private, versioned evidence history. Standard library; no network or secrets."""
from __future__ import annotations

import copy
import json
import sqlite3
import uuid
from pathlib import Path

if __package__:
    from .common import clean_text, valid_records
    from .coverage import build_coverage, row_state
    from .evidence_bundle import canonical, digest, time_value, redact_contacts
else:
    from common import clean_text, valid_records
    from coverage import build_coverage, row_state
    from evidence_bundle import canonical, digest, time_value, redact_contacts


def collection_rows(data):
    """Whitelist source evidence, including valid rows from partial fetches."""
    rows = []
    for book in data['notebooks']['bookNotes']:
        book_id = str(book.get('bookId') or '')
        for field, kind, text_key, id_key, chapter_key in (
            ('reviews', 'personal_review', 'content', 'reviewId', 'chapterName'),
            ('underlines', 'underline', 'text', 'bookmarkId', 'chapterTitle'),
        ):
            for source in valid_records(book, field):
                text = clean_text(source.get(text_key))
                if not text or source.get('error'):
                    continue
                rows.append({
                    'kind': kind, 'source_id': str(source.get(id_key) or ''),
                    'book_id': book_id, 'title': clean_text(book.get('title')),
                    'author': clean_text(book.get('author')), 'chapter': clean_text(source.get(chapter_key)),
                    'text': text, 'created_at': time_value(source.get('createTime')),
                    'modified_at': time_value(source.get('updateTime')),
                    'fetch_state': row_state(book, field),
                })
    return rows


class HistoryStore:
    """One directory per dataset/account. Source IDs never leave the local store."""
    def __init__(self, directory: Path):
        self.directory = Path(directory).resolve()
        if self.directory.name.startswith('.env'):
            raise ValueError('Credential paths are not history stores')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.directory / 'history.sqlite3')
        self.db.execute('PRAGMA foreign_keys=ON')
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone():
            previous_schema = self.db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if not previous_schema or previous_schema[0] not in {'1.0', '1.1'}:
                self.close()
                raise ValueError('Unsupported history schema')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY, observed TEXT NOT NULL, coverage TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY, entity TEXT NOT NULL, body TEXT NOT NULL, first_snapshot INTEGER NOT NULL REFERENCES snapshots(id));
            CREATE TABLE IF NOT EXISTS sightings(snapshot INTEGER REFERENCES snapshots(id), version TEXT REFERENCES versions(id), metadata TEXT NOT NULL, PRIMARY KEY(snapshot,version));
            CREATE INDEX IF NOT EXISTS sightings_by_version ON sightings(version,snapshot);
            CREATE INDEX IF NOT EXISTS versions_by_entity ON versions(entity);
            CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS question_index(id TEXT PRIMARY KEY, label TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS proposition_index(id TEXT PRIMARY KEY, version TEXT NOT NULL REFERENCES versions(id), question TEXT NOT NULL REFERENCES question_index(id), body TEXT NOT NULL);
        ''')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)', ('schema_version', '1.1'))
            self.db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)', ('dataset_id', str(uuid.uuid4())))
        if self.db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] not in {'1.0', '1.1'}:
            self.close()
            raise ValueError('Unsupported history schema')
        with self.db:
            self.db.execute("UPDATE meta SET value='1.1' WHERE key='schema_version'")
        self.dataset_id = self.db.execute("SELECT value FROM meta WHERE key='dataset_id'").fetchone()[0]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.db.close()

    def ingest(self, data):
        observed = time_value(data.get('generatedAt'))
        if observed is None:
            raise ValueError('Snapshot requires a timezone-aware collection time')
        previous = self.db.execute('SELECT observed FROM snapshots ORDER BY id DESC LIMIT 1').fetchone()
        if previous and observed < previous[0]:
            raise ValueError('Snapshots must be collected in chronological order')
        rows = collection_rows(data)
        coverage = build_coverage(data, sum(r['kind'] == 'underline' for r in rows),
                                  sum(r['kind'] == 'personal_review' for r in rows))
        prepared, seen = [], {}
        for row in rows:
            identity = 'stable' if row['source_id'] and row['book_id'] else 'provisional'
            identity_body = [self.dataset_id, row['kind'], row['book_id'], row['source_id']]
            if identity == 'provisional':
                identity_body += [row['created_at'], row['chapter'], row['text']]
            entity_id = 'entity-' + digest(identity_body)[:32]
            body = {k: row[k] for k in ('kind', 'chapter', 'text', 'created_at', 'modified_at')}
            body.update(entity_id=entity_id, identity=identity,
                        book_ref='book-' + digest([self.dataset_id, row['book_id']])[:24])
            version_id = 'version-' + digest(body)[:32]
            if entity_id in seen:
                if seen[entity_id] != version_id:
                    raise ValueError('Conflicting source versions in one snapshot')
                continue
            seen[entity_id] = version_id
            metadata = {k: row[k] for k in ('title', 'author', 'fetch_state')}
            prepared.append((entity_id, version_id, body, metadata))
        with self.db:
            cursor = self.db.execute('INSERT INTO snapshots(observed,coverage) VALUES (?,?)', (observed, canonical(coverage)))
            snapshot = cursor.lastrowid
            for entity, version, body, metadata in prepared:
                last = self.db.execute('SELECT v.id FROM versions v JOIN sightings s ON s.version=v.id WHERE v.entity=? ORDER BY s.snapshot DESC LIMIT 1', (entity,)).fetchone()
                if last and last[0] != version:
                    metadata['observed_edit'] = True
                self.db.execute('INSERT OR IGNORE INTO versions VALUES (?,?,?,?)', (version, entity, canonical(body), snapshot))
                self.db.execute('INSERT INTO sightings VALUES (?,?,?)', (snapshot, version, canonical(metadata)))
        return snapshot

    def versions(self):
        output = []
        latest = self.db.execute('SELECT MAX(id) FROM snapshots').fetchone()[0]
        for version, body_json, first_id, first_time in self.db.execute('''
            SELECT v.id,v.body,v.first_snapshot,s.observed FROM versions v
            JOIN snapshots s ON s.id=v.first_snapshot ORDER BY v.id'''):
            body = json.loads(body_json)
            last_id, metadata_json, last_time = self.db.execute('SELECT si.snapshot,si.metadata,s.observed FROM sightings si JOIN snapshots s ON s.id=si.snapshot WHERE version=? ORDER BY si.snapshot DESC LIMIT 1', (version,)).fetchone()
            metadata = json.loads(metadata_json)
            first_meta = json.loads(self.db.execute('SELECT metadata FROM sightings WHERE version=? AND snapshot=?', (version, first_id)).fetchone()[0])
            # Never re-date an observed edit to the old creation time. Source modification
            # dates may precede our first observation, but cannot be asserted as original content.
            if metadata.get('observed_edit') and last_id != first_id:
                effective, basis = last_time, 'observed_edit'
            elif first_meta.get('observed_edit'):
                effective, basis = body['modified_at'] or first_time, 'source_modified' if body['modified_at'] else 'observed_edit'
            elif body['modified_at']:
                effective, basis = body['modified_at'], 'source_modified'
            else:
                effective, basis = body['created_at'], 'created_version_unknown' if body['created_at'] else 'unknown'
            if (effective and effective > last_time) or (body['created_at'] and body['modified_at'] and body['modified_at'] < body['created_at']):
                effective, basis = None, 'unknown'
            body.update(version_id=version, title=metadata['title'], author=metadata['author'],
                        fetch_state=metadata['fetch_state'], first_observed_at=first_time,
                        effective_at=effective, time_basis=basis, historical_version_unknown=True,
                        visibility='observed' if last_id == latest else 'not_observed',
                        last_snapshot=last_id, first_snapshot=first_id)
            output.append(body)
        return output

    def export(self):
        all_versions = self.versions()
        latest = {}
        for note in all_versions:
            old = latest.get(note['entity_id'])
            if old is None or note['last_snapshot'] > old['last_snapshot']:
                latest[note['entity_id']] = note
        snapshot = self.db.execute('SELECT id,observed,coverage FROM snapshots ORDER BY id DESC LIMIT 1').fetchone()
        body = {'schema_version': 'evolution-history-1.0', 'dataset_id': self.dataset_id,
                'snapshot_count': self.db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0],
                'observed_at': snapshot[1] if snapshot else None,
                'collection_coverage': json.loads(snapshot[2]) if snapshot else None,
                'notes': sorted(latest.values(), key=lambda n: n['version_id']),
                'feedback': self.feedback_log(),
                'privacy_notice': 'Private reading content; masking is not full anonymization.'}
        # Mask the exported analysis representation, not the private source-version identity.
        for note in body['notes']:
            for key in ('text', 'title', 'author', 'chapter'):
                note[key] = redact_contacts(note[key])
        for entry in body['feedback']:
            for key in ('explanation', 'question', 'reviewed_explanation'):
                if key in entry: entry[key] = redact_contacts(entry[key])
        body['input_digest'] = digest(body)
        return body

    def export_versions(self):
        rows = self.versions()
        for note in rows:
            for key in ('text', 'title', 'author', 'chapter'):
                note[key] = redact_contacts(note[key])
        return rows

    def feedback_log(self):
        return [json.loads(row[0]) for row in self.db.execute('SELECT body FROM feedback ORDER BY id')]

    def append_feedback(self, fingerprint, body):
        with self.db:
            self.db.execute('INSERT INTO feedback(fingerprint,body) VALUES (?,?)', (fingerprint, canonical(body)))

    def get_cached(self, key):
        row = self.db.execute('SELECT body FROM cache WHERE key=?', (key,)).fetchone()
        try:
            return json.loads(row[0]) if row else None
        except (ValueError, TypeError):
            return None

    def cache_response(self, key, result):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO cache VALUES (?,?)', (key, canonical(result)))

    def index_propositions(self, observations):
        import re
        with self.db:
            for row in observations:
                if row['voice'] != 'own': continue
                # Called only after extraction validation. Identity is a normalized label,
                # not a claim that semantic synonyms have been exhaustively merged.
                key = re.sub(r'[^\w\u4e00-\u9fff]', '', row['question']).casefold()
                question = 'question-' + digest([self.dataset_id, key])[:24]
                self.db.execute('INSERT OR IGNORE INTO question_index VALUES (?,?)', (question, row['question']))
                self.db.execute('INSERT OR REPLACE INTO proposition_index VALUES (?,?,?,?)',
                                (row['id'], row['version_id'], question, canonical(row)))

    def problem_index(self):
        return [{'id': row[0], 'question': row[1], 'propositions': row[2]} for row in self.db.execute(
            'SELECT q.id,q.label,COUNT(p.id) FROM question_index q LEFT JOIN proposition_index p ON p.question=q.id GROUP BY q.id ORDER BY q.id')]

    def clear(self):
        """Clear this database only; exports/reports/backups require separate removal."""
        with self.db:
            self.db.execute('PRAGMA secure_delete=ON')
            for table in ('proposition_index', 'question_index', 'cache', 'feedback', 'sightings', 'versions', 'snapshots'):
                self.db.execute('DELETE FROM ' + table)
        self.db.execute('VACUUM')
