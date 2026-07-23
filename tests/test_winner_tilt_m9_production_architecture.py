from dataclasses import replace

from winner_tilt.data_providers import MarketDataProvider, ProviderResult, validate_provider_config
from winner_tilt.validation import validate_provider_result, validate_config
from winner_tilt.snapshot_manager import SnapshotManager, SnapshotIntegrityError, canonical_json
from winner_tilt.scheduler import ProductionScheduler, STAGE_ORDER
from winner_tilt.health import calculate_health
from winner_tilt.operational_logging import log_record

ACQ = "2026-07-23T12:00:00Z"
EFF = "2026-07-23T00:00:00Z"
PUB = "2026-07-23T01:00:00Z"


def provider(rows=None, **kw):
    return MarketDataProvider(
        rows or [{"id": "WTI", "security_id": "ABC", "price": 1}],
        acquired_at=kw.get("acq", ACQ),
        effective_at=kw.get("eff", EFF),
        published_at=kw.get("pub", PUB),
        provenance=kw.get("prov", {"source_reference": "synthetic://x", "retrieval_method": "in_memory", "license": "synthetic"}),
    )


def required_adapters(calls=None):
    calls = calls if calls is not None else []
    return {name: (lambda ctx, n=name: calls.append(n) or {"ok": n}) for name in STAGE_ORDER[3:]}


def test_provider_contract_metadata_and_timestamps():
    p = provider()
    r = p.fetch()
    assert p.metadata().contract_version == "1.0.0"
    assert r.provider_id and r.vendor and r.acquisition_timestamp == ACQ and r.effective_timestamp == EFF and r.publication_timestamp == PUB
    assert p.latest_timestamp() == PUB
    assert p.validate(r).status == "PASS"


def test_invalid_provider_outputs_fail_closed():
    r = ProviderResult("market_data", (), "", "vendor", ACQ, EFF, "9.9.9", {}, "unvalidated", PUB)
    result = validate_provider_result(r, cutoff_timestamp=ACQ)
    assert result.status == "FAIL_CLOSED"
    assert "SCHEMA_VERSION_MISMATCH" in result.errors and "MISSING_OR_INVALID_PROVENANCE" in result.errors


def test_validation_stale_future_timestamp_ordering_duplicates_malformed_provenance():
    p = provider([{"id": "bad id"}, {"id": "bad id"}], acq=ACQ, eff="2026-07-01T00:00:00Z", pub="2026-07-24T00:00:00Z", prov={})
    result = validate_provider_result(p.fetch(), cutoff_timestamp=ACQ, max_staleness_days=1, natural_key_fields=("id",))
    assert result.status == "FAIL_CLOSED"
    assert {"STALE_DATA", "PUBLICATION_AFTER_ACQUISITION", "FUTURE_DATED_PUBLICATION", "DUPLICATE_NATURAL_KEY", "MALFORMED_IDENTIFIER", "MISSING_OR_INVALID_PROVENANCE"} <= set(result.errors)
    assert result.fingerprint == validate_provider_result(p.fetch(), cutoff_timestamp=ACQ, max_staleness_days=1, natural_key_fields=("id",)).fingerprint


def test_provenance_required_fields_are_configuration_driven():
    r = provider(prov={"source_reference": "synthetic://x", "retrieval_method": "in_memory"}).fetch()
    result = validate_provider_result(r, validation_config={"required_provenance_fields": ["source_reference", "retrieval_method", "license"]})
    assert result.status == "FAIL_CLOSED"
    assert "MISSING_PROVENANCE_LICENSE" in result.errors
    relaxed = validate_provider_result(r, validation_config={"required_provenance_fields": ["source_reference", "retrieval_method"]})
    assert relaxed.status == "PASS"


def test_duplicate_detection_requires_explicit_natural_keys_and_serializes_nested_values():
    rows = [{"id": "A", "period": {"year": 2026, "quarter": 1}}, {"id": "A", "period": {"quarter": 1, "year": 2026}}]
    r = provider(rows).fetch()
    assert validate_provider_result(r, natural_key_fields=()).status == "FAIL_CLOSED"
    result = validate_provider_result(r, natural_key_fields=("id", "period"))
    assert result.status == "FAIL_CLOSED"
    assert "DUPLICATE_NATURAL_KEY" in result.errors


def test_config_rejects_unknown_nested_settings_and_literal_secrets():
    valid = {"schema_version": "1.0.0", "config_version": "1.0.0", "providers": [{"dataset_type": "x", "provider_id": "p", "vendor": "v", "enabled": True, "api_key": "${VENDOR_API_KEY}"}], "environment_placeholders": [], "live_integrations_enabled": False}
    assert validate_provider_config(valid)
    bad_secret = valid | {"providers": [{"dataset_type": "x", "provider_id": "p", "vendor": "v", "enabled": True, "api_key": "literal-secret", "credential_env_var": "env"}]}
    try:
        validate_provider_config(bad_secret)
    except ValueError as exc:
        assert "SECRET_VALUE_NOT_ALLOWED" in str(exc)
    else:
        raise AssertionError("literal secret must fail closed")
    bad_unknown = valid | {"providers": [{"dataset_type": "x", "provider_id": "p", "vendor": "v", "enabled": True, "nested_unknown": True}]}
    try:
        validate_provider_config(bad_unknown)
    except ValueError as exc:
        assert "UNKNOWN_PROVIDER_CONFIG_SETTING" in str(exc)
    else:
        raise AssertionError("unknown nested setting must fail closed")
    assert validate_config({"schema_version": "1", "config_version": "1"}, {"schema_version", "config_version"}).status == "PASS"
    assert validate_config({"schema_version": "1", "config_version": "1", "x": 1}, {"schema_version", "config_version"}).status == "FAIL_CLOSED"


def test_snapshot_hashing_canonical_duplicate_immutability_integrity_and_journal_reference():
    sm = SnapshotManager()
    payload = {"b": 2, "a": 1}
    assert canonical_json(payload) == '{"a":1,"b":2}'
    rec = sm.create_snapshot("market_data", payload, acquisition_timestamp=ACQ, publication_timestamp=PUB, effective_timestamp=EFF, cutoff_timestamp=ACQ, source_references=["synthetic://x"])
    rec2 = sm.create_snapshot("market_data", {"a": 1, "b": 2}, acquisition_timestamp=ACQ, publication_timestamp=PUB, effective_timestamp=EFF, cutoff_timestamp=ACQ, source_references=["synthetic://x"])
    assert rec == rec2 and sm.verify_integrity(rec, payload)
    assert sm.expected_metadata_sha256(rec) == rec.metadata_sha256
    assert sm.expected_snapshot_id(dataset_type=rec.dataset_type, content_sha256=rec.content_sha256, effective_timestamp=rec.effective_timestamp, cutoff_timestamp=rec.cutoff_timestamp, source_references=rec.source_references) == rec.snapshot_id
    ref = sm.decision_journal_source_reference(rec)
    assert ref["snapshot_id"] == rec.snapshot_id and ref["content_sha256"] == rec.content_sha256
    try:
        sm.verify_integrity(rec, {"a": 2})
    except SnapshotIntegrityError as exc:
        assert "CONTENT_HASH_MISMATCH" in str(exc)
    else:
        raise AssertionError("expected fail closed")


def test_snapshot_rejects_empty_sources_invalid_timestamps_and_tampered_metadata():
    sm = SnapshotManager()
    try:
        sm.create_snapshot("market_data", {}, acquisition_timestamp=ACQ, publication_timestamp=PUB, effective_timestamp=EFF, cutoff_timestamp=ACQ, source_references=[])
    except SnapshotIntegrityError as exc:
        assert "SOURCE_REFERENCES_REQUIRED" in str(exc)
    else:
        raise AssertionError("empty sources must fail closed")
    try:
        sm.create_snapshot("market_data", {}, acquisition_timestamp=ACQ, publication_timestamp="2026-07-24T00:00:00Z", effective_timestamp=EFF, cutoff_timestamp=ACQ, source_references=["synthetic://x"])
    except SnapshotIntegrityError as exc:
        assert "PUBLICATION_AFTER_ACQUISITION" in str(exc)
    else:
        raise AssertionError("invalid timestamp order must fail closed")
    rec = sm.create_snapshot("market_data", {}, acquisition_timestamp=ACQ, publication_timestamp=PUB, effective_timestamp=EFF, cutoff_timestamp=ACQ, source_references=["synthetic://x"])
    tampered = replace(rec, metadata_sha256="0" * 64)
    sm._manifest[rec.snapshot_id] = tampered
    try:
        sm.verify_integrity(tampered, {})
    except SnapshotIntegrityError as exc:
        assert "METADATA_HASH_MISMATCH" in str(exc)
    else:
        raise AssertionError("tampered metadata must fail closed")


def test_scheduler_stage_order_failure_dependency_injection_and_non_interference():
    sm = SnapshotManager()
    calls = []
    run = ProductionScheduler(providers=[provider()], snapshot_manager=sm, adapters=required_adapters(calls), clock=lambda: ACQ, execution_id_factory=lambda: "exec-1").run(ACQ)
    assert run.status == "PASS" and [s.name for s in run.stages] == list(STAGE_ORDER)
    assert run.execution_id == "exec-1" and calls == list(STAGE_ORDER[3:]) and not any(run.non_interference.values())
    bad = ProductionScheduler(providers=[provider(prov={})], snapshot_manager=sm, adapters=required_adapters(), clock=lambda: ACQ, execution_id_factory=lambda: "exec-2").run(ACQ)
    assert bad.status == "FAIL_CLOSED" and [s.name for s in bad.stages] == ["acquire_data", "validate_data"]


def test_scheduler_missing_required_adapter_fails_closed_and_stops_downstream():
    run = ProductionScheduler(providers=[provider()], snapshot_manager=SnapshotManager(), adapters={"universe_engine": lambda ctx: {"ok": True}}, clock=lambda: ACQ, execution_id_factory=lambda: "exec-3").run(ACQ)
    assert run.status == "FAIL_CLOSED"
    assert [stage.name for stage in run.stages] == ["acquire_data", "validate_data", "create_snapshots", "universe_engine", "scoring_engine"]
    assert run.stages[-1].status == "FAIL" and "MISSING_REQUIRED_ADAPTER:scoring_engine" in run.stages[-1].error


def test_scheduler_execution_fingerprint_deterministic_independent_from_unique_id():
    adapters = required_adapters()
    run1 = ProductionScheduler(providers=[provider()], snapshot_manager=SnapshotManager(), adapters=adapters, clock=lambda: ACQ, execution_id_factory=lambda: "unique-1").run(ACQ)
    run2 = ProductionScheduler(providers=[provider()], snapshot_manager=SnapshotManager(), adapters=adapters, clock=lambda: ACQ, execution_id_factory=lambda: "unique-2").run(ACQ)
    assert run1.execution_id != run2.execution_id
    assert run1.execution_fingerprint == run2.execution_fingerprint


def test_health_state_and_production_blockers():
    h = calculate_health(provider_configs_ok=True, provider_contract_available=True, synthetic_provider_available=True, live_provider_available=False, snapshot_fresh=True, validation_failures=0, required_dataset_coverage=True, dashboard_inputs_available=True, decision_journal_integrity=True)
    assert h.state == "degraded" and not h.production_ready and "live vendor integrations absent" in h.blockers
    assert h.checks["provider_contract_availability"] == "healthy" and h.checks["synthetic_offline_provider_availability"] == "healthy"
    f = calculate_health(provider_configs_ok=False, provider_contract_available=True, synthetic_provider_available=True, live_provider_available=False, snapshot_fresh=True, validation_failures=1, required_dataset_coverage=True, dashboard_inputs_available=True, decision_journal_integrity=True)
    assert f.state == "failed"


def test_operational_logging_redacts_secrets_recursively_and_in_exceptions():
    message = "api_key=123 token=abc authorization=Bearer password=p secret=s credential=c"
    rec = log_record(
        execution_id="e",
        stage="validate",
        severity="ERROR",
        event_code="X",
        context={"api_key": "123", "nested": {"token": "abc", "items": ("authorization=Bearer", {"password": "p"}), "set": {"secret=s", "ok"}}},
        exception=ValueError(message),
        timestamp=ACQ,
    )
    assert rec["context"]["api_key"] == "[REDACTED]"
    assert rec["context"]["nested"]["token"] == "[REDACTED]"
    assert rec["context"]["nested"]["items"][0] == "authorization=[REDACTED]"
    assert rec["context"]["nested"]["items"][1]["password"] == "[REDACTED]"
    assert "secret=[REDACTED]" in rec["context"]["nested"]["set"]
    assert "api_key=[REDACTED]" in rec["exception"]["message"]
    assert "token=[REDACTED]" in rec["exception"]["message"]
    assert "authorization=[REDACTED]" in rec["exception"]["message"]
    assert "password=[REDACTED]" in rec["exception"]["message"]
    assert "secret=[REDACTED]" in rec["exception"]["message"]
    assert "credential=[REDACTED]" in rec["exception"]["message"]
