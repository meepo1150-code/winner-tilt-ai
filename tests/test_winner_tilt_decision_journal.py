import copy, json
from pathlib import Path
import pytest
from winner_tilt.decision_journal import JournalStore, JournalValidationError, construct_record, file_ref, record_hash, validate_record

ROOT = Path('.')
TS = '2026-07-23T00:00:00Z'

def sample_record():
    score = json.loads(Path('reports/winner-tilt-prototype-score-run-v1.0.json').read_text())
    portfolio = json.loads(Path('reports/winner-tilt-prototype-portfolio-run-v1.0.json').read_text())
    uni = file_ref('database/universe-v1.0.csv', root=ROOT, snapshot_timestamp_utc=TS)
    sref = file_ref('reports/winner-tilt-prototype-score-run-v1.0.json', root=ROOT, run_id='score-run', snapshot_timestamp_utc=TS)
    pref = file_ref('reports/winner-tilt-prototype-portfolio-run-v1.0.json', root=ROOT, run_id='portfolio-run', snapshot_timestamp_utc=TS)
    return construct_record(
        decision_type='semiannual_rebalance', run_id='unit-run', decision_timestamp_utc=TS,
        effective_date='2026-07-23', as_of_date='2026-07-23', input_data_cutoff_utc=TS,
        system_identifiers={'engine':'journal-test'}, config_identifiers={'cfg':'abc'},
        source_snapshot_identifiers={'score':sref['sha256']}, universe_snapshot_ref=uni, score_run_ref=sref,
        portfolio_run_ref=pref, score_run=score, portfolio_run=portfolio,
        validation_status='VALIDATION_ONLY_SYNTHETIC_PROTOTYPE', synthetic_prototype=True,
        rationale_evidence_refs=[sref, pref])

def test_deterministic_construction_and_canonical_hashing():
    a = sample_record(); b = sample_record()
    assert a == b
    assert a['immutable_record_hash'] == record_hash(a)
    shuffled = dict(reversed(list(a.items())))
    shuffled['immutable_record_hash'] = a['immutable_record_hash']
    validate_record(shuffled)

def test_input_immutability():
    score = json.loads(Path('reports/winner-tilt-prototype-score-run-v1.0.json').read_text())
    portfolio = json.loads(Path('reports/winner-tilt-prototype-portfolio-run-v1.0.json').read_text())
    before = copy.deepcopy((score, portfolio))
    r = sample_record()
    assert r['selected_holdings']
    assert before == (score, portfolio)

def test_duplicate_detection_append_only_and_integrity(tmp_path):
    store = JournalStore(tmp_path.relative_to(tmp_path) / 'journal.jsonl')
    store.path = tmp_path / 'journal.jsonl'
    r = sample_record()
    store.append(r)
    size = store.path.stat().st_size
    with pytest.raises(JournalValidationError, match='duplicate'):
        store.append(r)
    assert store.path.stat().st_size == size
    integrity = store.verify_integrity()
    assert integrity['valid'] is True and integrity['record_count'] == 1

def test_missing_required_fields_invalid_timestamp_and_future_information():
    r = sample_record(); r.pop('run_id')
    with pytest.raises(JournalValidationError, match='missing required fields'):
        validate_record(r)
    r = sample_record(); r['input_data_cutoff_utc'] = '2026-07-24T00:00:00Z'
    with pytest.raises(JournalValidationError, match='cannot be after'):
        validate_record(r)
    r = sample_record(); r['score_run_ref']['snapshot_timestamp_utc'] = '2026-07-24T00:00:00Z'; r['immutable_record_hash'] = record_hash(r)
    with pytest.raises(JournalValidationError, match='future-dated'):
        validate_record(r)

def test_mismatched_run_references_and_absolute_paths_rejected():
    with pytest.raises(JournalValidationError, match='repository-relative'):
        file_ref('/tmp/nope.json', root=ROOT, snapshot_timestamp_utc=TS)
    r = sample_record(); r['score_run_ref']['run_id'] = 3; r['immutable_record_hash'] = record_hash(r)
    with pytest.raises(JournalValidationError, match='run_id'):
        validate_record(r)

def test_synthetic_warning_and_no_interference_required():
    r = sample_record(); r['warnings'] = []; r['immutable_record_hash'] = record_hash(r)
    with pytest.raises(JournalValidationError, match='not investment evidence'):
        validate_record(r)
    r = sample_record(); r['non_interference_attestation']['scoring_modified'] = True; r['immutable_record_hash'] = record_hash(r)
    with pytest.raises(JournalValidationError, match='non-interference'):
        validate_record(r)
