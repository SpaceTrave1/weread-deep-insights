"""Append-only human feedback and revalidated host-result reuse."""
import copy
from datetime import datetime, timezone

if __package__:
    from .evolution_analysis import validate_report, validate_history, validate_response, accepted_results, require, normalized
else:
    from evolution_analysis import validate_report, validate_history, validate_response, accepted_results, require, normalized

FEEDBACK_STATES = ('confirmed', 'rejected', 'clarified', 'needs_context')


def record_feedback(store, report, entry):
    validate_report(report)
    require(store.dataset_id == report['history']['dataset_id'], 'Feedback belongs to a different dataset')
    require(isinstance(entry, dict) and set(entry) == {'trajectory_id', 'status', 'explanation'}, 'Unexpected feedback fields')
    require(entry['status'] in FEEDBACK_STATES and isinstance(entry['explanation'], str)
            and len(entry['explanation']) <= 4000, 'Invalid feedback status/text')
    require(entry['status'] != 'clarified' or entry['explanation'].strip(), 'Clarification needs an explanation')
    trajectory = next((t for t in report['trajectories'] if t['id'] == entry['trajectory_id']), None)
    require(trajectory is not None, 'Unknown trajectory')
    known = {n['version_id']: n['entity_id'] for n in store.versions()}
    require(all(known.get(n['version_id']) == n['entity_id'] for n in trajectory['notes']), 'Feedback source versions are not in this history')
    body = dict(entry, entity_ids=[n['entity_id'] for n in trajectory['notes']],
                version_ids=[n['version_id'] for n in trajectory['notes']], question=trajectory['question'],
                reviewed_explanation=trajectory['explanation'],
                relation=trajectory['relation'], recorded_at=datetime.now(timezone.utc).isoformat(),
                attribution='user feedback; not independently verified evidence')
    store.append_feedback(trajectory['id'], body)
    return body


def feedback_view(report, current_history=None):
    validate_report(report)
    current = validate_history(current_history or report['history'])
    require(current['dataset_id'] == report['history']['dataset_id'], 'Report/history datasets differ')
    latest_versions = {n['entity_id']: n['version_id'] for n in current['notes']}
    latest_feedback = {f['trajectory_id']: f for f in current['feedback']}
    rows = copy.deepcopy(report['trajectories'])
    for row in rows:
        row['feedback'] = latest_feedback.get(row['id'])
        entities = {n['entity_id'] for n in row['notes']}
        row['related_feedback'] = [f for f in current['feedback'] if f['trajectory_id'] != row['id']
                                   and entities == set(f.get('entity_ids', []))]
        row['needs_review'] = any(latest_versions.get(n['entity_id']) != n['version_id'] for n in row['notes'])
        if any(set(f.get('version_ids', [])) != {n['version_id'] for n in row['notes']} for f in row['related_feedback']):
            row['needs_review'] = True
        if any(normalized(f.get('question', '')) == normalized(row['question']) for f in row['related_feedback']):
            row['needs_review'] = True  # Different model explanation must not inherit confirmation.
    return rows


def cached_results(store, plan):
    output = []
    for request in plan['requests']:
        result = store.get_cached(request['input_digest'])
        if result is not None:
            try:
                output.append(validate_response(result, request))
            except (ValueError, KeyError, TypeError):
                pass  # Invalid cache is never counted as processed evidence.
    return output


def cache_results(store, plan, results):
    accepted = accepted_results(plan, results)
    for request, result in accepted:
        if result['status'] == 'complete':
            store.cache_response(request['input_digest'], result)
