from winner_tilt.data_providers import MarketDataProvider, ProviderResult, validate_provider_config
from winner_tilt.validation import validate_provider_result, validate_config
from winner_tilt.snapshot_manager import SnapshotManager, SnapshotIntegrityError, canonical_json
from winner_tilt.scheduler import ProductionScheduler, STAGE_ORDER
from winner_tilt.health import calculate_health
from winner_tilt.operational_logging import log_record

ACQ="2026-07-23T12:00:00Z"; EFF="2026-07-23T00:00:00Z"; PUB="2026-07-23T01:00:00Z"

def provider(rows=None, **kw):
    return MarketDataProvider(rows or [{"id":"WTI","security_id":"ABC","price":1}], acquired_at=kw.get("acq",ACQ), effective_at=kw.get("eff",EFF), published_at=kw.get("pub",PUB), provenance=kw.get("prov", {"source_reference":"synthetic://x","retrieval_method":"in_memory","license":"synthetic"}))

def test_provider_contract_metadata_and_timestamps():
    p=provider(); r=p.fetch()
    assert p.metadata().contract_version=="1.0.0"
    assert r.provider_id and r.vendor and r.acquisition_timestamp==ACQ and r.effective_timestamp==EFF and r.publication_timestamp==PUB
    assert p.latest_timestamp()==PUB
    assert p.validate(r).status=="PASS"

def test_invalid_provider_outputs_fail_closed():
    r=ProviderResult("market_data",(),"","vendor",ACQ,EFF,"9.9.9",{},"unvalidated",PUB)
    result=validate_provider_result(r, cutoff_timestamp=ACQ)
    assert result.status=="FAIL_CLOSED"
    assert "SCHEMA_VERSION_MISMATCH" in result.errors and "MISSING_OR_INVALID_PROVENANCE" in result.errors

def test_validation_stale_future_timestamp_ordering_duplicates_malformed_provenance():
    p=provider([{"id":"bad id"},{"id":"bad id"}], acq="2026-07-23T12:00:00Z", eff="2026-07-01T00:00:00Z", pub="2026-07-24T00:00:00Z", prov={})
    result=validate_provider_result(p.fetch(), cutoff_timestamp=ACQ, max_staleness_days=1)
    assert result.status=="FAIL_CLOSED"
    assert {"STALE_DATA","PUBLICATION_AFTER_ACQUISITION","FUTURE_DATED_PUBLICATION","DUPLICATE_OBSERVATION","MALFORMED_IDENTIFIER","MISSING_OR_INVALID_PROVENANCE"} <= set(result.errors)
    assert result.fingerprint == validate_provider_result(p.fetch(), cutoff_timestamp=ACQ, max_staleness_days=1).fingerprint

def test_config_rejects_unknown_and_provider_config_unsafe():
    assert validate_config({"schema_version":"1","config_version":"1"},{"schema_version","config_version"}).status=="PASS"
    assert validate_config({"schema_version":"1","config_version":"1","x":1},{"schema_version","config_version"}).status=="FAIL_CLOSED"
    assert validate_provider_config({"schema_version":"1","config_version":"1","providers":[],"environment_placeholders":[],"live_integrations_enabled":False})

def test_snapshot_hashing_canonical_duplicate_immutability_integrity_and_journal_reference():
    sm=SnapshotManager(); payload={"b":2,"a":1}
    assert canonical_json(payload)=='{"a":1,"b":2}'
    rec=sm.create_snapshot("market_data",payload,acquisition_timestamp=ACQ,publication_timestamp=PUB,effective_timestamp=EFF,cutoff_timestamp=ACQ,source_references=["synthetic://x"])
    rec2=sm.create_snapshot("market_data",{"a":1,"b":2},acquisition_timestamp=ACQ,publication_timestamp=PUB,effective_timestamp=EFF,cutoff_timestamp=ACQ,source_references=["synthetic://x"])
    assert rec==rec2 and sm.verify_integrity(rec,payload)
    ref=sm.decision_journal_source_reference(rec)
    assert ref["snapshot_id"]==rec.snapshot_id and ref["content_sha256"]==rec.content_sha256
    try: sm.verify_integrity(rec,{"a":2})
    except SnapshotIntegrityError as exc: assert "CONTENT_HASH_MISMATCH" in str(exc)
    else: raise AssertionError("expected fail closed")

def test_scheduler_stage_order_failure_dependency_injection_and_non_interference():
    sm=SnapshotManager(); calls=[]
    adapters={name:(lambda ctx,n=name: calls.append(n) or {"ok":n}) for name in STAGE_ORDER[3:]}
    run=ProductionScheduler(providers=[provider()], snapshot_manager=sm, adapters=adapters, clock=lambda: ACQ).run(ACQ)
    assert run.status=="PASS" and [s.name for s in run.stages]==list(STAGE_ORDER)
    assert calls==list(STAGE_ORDER[3:]) and not any(run.non_interference.values())
    bad=ProductionScheduler(providers=[provider(prov={})], snapshot_manager=sm, clock=lambda: ACQ).run(ACQ)
    assert bad.status=="FAIL_CLOSED" and [s.name for s in bad.stages]==["acquire_data","validate_data"]

def test_health_state_and_production_blockers():
    h=calculate_health(provider_configs_ok=True,provider_available=True,snapshot_fresh=True,validation_failures=0,required_dataset_coverage=True,dashboard_inputs_available=True,decision_journal_integrity=True)
    assert h.state=="degraded" and not h.production_ready and "live vendor integrations absent" in h.blockers
    f=calculate_health(provider_configs_ok=False,provider_available=True,snapshot_fresh=True,validation_failures=1,required_dataset_coverage=True,dashboard_inputs_available=True,decision_journal_integrity=True)
    assert f.state=="failed"

def test_operational_logging_redacts_secrets_and_records_exception():
    rec=log_record(execution_id="e",stage="validate",severity="ERROR",event_code="X",context={"api_key":"123","nested":{"token":"abc","ok":1}},exception=ValueError("bad"),timestamp=ACQ)
    assert rec["context"]["api_key"]=="[REDACTED]" and rec["context"]["nested"]["token"]=="[REDACTED]"
    assert rec["exception"]["type"]=="ValueError"
