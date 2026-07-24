import json
from pathlib import Path

import pytest

from winner_tilt.multi_cik_live import (
    AUTHORIZATION_PHRASE,
    MultiCikLiveError,
    build_aggregate_snapshot,
    build_authorization_gate,
    finalize_live_bundle,
    parse_authorized_ciks,
)


def write_registry(path: Path):
    path.write_text(
        "cik,security_id,ticker,status,effective_from,effective_to,source\n"
        "0000320193,WT-0005,AAPL,ACTIVE,2026-07-24,,SEC\n"
        "0000789019,WT-0001,MSFT,ACTIVE,2026-07-24,,SEC\n"
        "0001045810,WT-0010,NVDA,ACTIVE,2026-07-24,,SEC\n",
        encoding="utf-8",
    )


def snapshot(cik: str, row_id: str, acquired: str):
    return {
        "dataset_type": "fundamentals",
        "provider_id": "sec-edgar-companyfacts",
        "acquisition_timestamp": acquired,
        "rows": [
            {
                "id": row_id,
                "cik": cik,
                "concept": "Revenue",
                "unit": "USD",
                "value": 1,
                "report_end": "2025-12-31",
                "accepted_timestamp": "2026-01-31T00:00:00Z",
                "accession_number": "0000000000-26-000001",
            }
        ],
        "provenance": {"raw_payload_retained": False, "raw_content_sha256": cik[-1] * 64},
        "pilot_tag": "ingest_only_no_downstream_consumption",
    }


def write_snapshot(root: Path, timestamp: str, cik: str, row_id: str, acquired: str):
    path = root / timestamp / f"CIK{cik}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot(cik, row_id, acquired)), encoding="utf-8")
    return path


def test_authorization_requires_exact_phrase_and_registry_membership(tmp_path):
    registry = tmp_path / "registry.csv"
    write_registry(registry)
    assert parse_authorized_ciks(
        "320193,789019", registry_path=registry, authorization=AUTHORIZATION_PHRASE
    ) == ("0000320193", "0000789019")
    with pytest.raises(MultiCikLiveError, match="MULTI_CIK_AUTHORIZATION_REQUIRED"):
        parse_authorized_ciks("320193", registry_path=registry, authorization="wrong")
    with pytest.raises(MultiCikLiveError, match="MULTI_CIK_UNREGISTERED"):
        parse_authorized_ciks("123", registry_path=registry, authorization=AUTHORIZATION_PHRASE)


def test_duplicate_and_request_overflow_fail_closed(tmp_path):
    registry = tmp_path / "registry.csv"
    write_registry(registry)
    with pytest.raises(MultiCikLiveError, match="MULTI_CIK_DUPLICATE_REQUEST"):
        parse_authorized_ciks(
            "320193,320193", registry_path=registry, authorization=AUTHORIZATION_PHRASE
        )
    with pytest.raises(MultiCikLiveError, match="MULTI_CIK_REQUEST_LIMIT_EXCEEDED"):
        parse_authorized_ciks(
            "320193,789019,1045810,1652044",
            registry_path=registry,
            authorization=AUTHORIZATION_PHRASE,
        )


def test_recursive_snapshot_discovery_and_deterministic_aggregation(tmp_path):
    registry = tmp_path / "registry.csv"
    write_registry(registry)
    gate = build_authorization_gate(
        ciks="0000320193,0000789019",
        authorization=AUTHORIZATION_PHRASE,
        registry_path=registry,
    )
    root = tmp_path / "runtime"
    write_snapshot(root, "20260724T060000Z", "0000320193", "a", "2026-07-24T06:00:00Z")
    write_snapshot(root, "20260724T060001Z", "0000789019", "b", "2026-07-24T06:00:01Z")
    first_snapshot, first_manifest = build_aggregate_snapshot(gate=gate, snapshot_dir=root)
    second_snapshot, second_manifest = build_aggregate_snapshot(gate=gate, snapshot_dir=root)
    assert first_snapshot == second_snapshot
    assert first_manifest == second_manifest
    assert first_manifest["snapshot_count"] == 2
    assert first_manifest["total_row_count"] == 2
    assert first_snapshot["acquisition_timestamp"] == "2026-07-24T06:00:01Z"
    assert [row["id"] for row in first_snapshot["rows"]] == ["a", "b"]


def test_missing_extra_and_duplicate_snapshot_fail_closed(tmp_path):
    registry = tmp_path / "registry.csv"
    write_registry(registry)
    gate = build_authorization_gate(
        ciks="0000320193,0000789019",
        authorization=AUTHORIZATION_PHRASE,
        registry_path=registry,
    )
    root = tmp_path / "runtime"
    write_snapshot(root, "ts1", "0000320193", "a", "2026-07-24T06:00:00Z")
    with pytest.raises(MultiCikLiveError, match="MULTI_CIK_SNAPSHOT_SET_MISMATCH"):
        build_aggregate_snapshot(gate=gate, snapshot_dir=root)
    write_snapshot(root, "ts2", "0000789019", "b", "2026-07-24T06:00:01Z")
    write_snapshot(root, "ts3", "0001045810", "c", "2026-07-24T06:00:02Z")
    with pytest.raises(MultiCikLiveError, match="MULTI_CIK_SNAPSHOT_SET_MISMATCH"):
        build_aggregate_snapshot(gate=gate, snapshot_dir=root)
    (root / "ts3" / "CIK0001045810.json").unlink()
    write_snapshot(root, "ts4", "0000320193", "d", "2026-07-24T06:00:03Z")
    with pytest.raises(MultiCikLiveError, match="MULTI_CIK_DUPLICATE_SNAPSHOT"):
        build_aggregate_snapshot(gate=gate, snapshot_dir=root)


def test_finalize_preserves_non_executable_boundary(tmp_path):
    registry = tmp_path / "registry.csv"
    write_registry(registry)
    gate = build_authorization_gate(
        ciks="0000320193", authorization=AUTHORIZATION_PHRASE, registry_path=registry
    )
    root = tmp_path / "runtime"
    write_snapshot(root, "ts", "0000320193", "a", "2026-07-24T06:00:00Z")
    aggregate, manifest = build_aggregate_snapshot(gate=gate, snapshot_dir=root)
    aggregate_path = tmp_path / "aggregate.json"
    aggregate_path.write_text(json.dumps(aggregate), encoding="utf-8")
    shadow_manifest = {
        "execution_boundary": {
            "broker_connected": False,
            "orders_created": False,
            "orders_executed": False,
            "automatic_dca": False,
            "automatic_exits": False,
        },
        "broker_integration_enabled": False,
    }
    result = finalize_live_bundle(
        gate=gate,
        aggregate_path=aggregate_path,
        aggregate_manifest=manifest,
        shadow_manifest=shadow_manifest,
    )
    assert result["status"] == "COMPLETED_AUTHORIZED_MULTI_CIK_SHADOW_RESEARCH_ONLY"
    assert result["snapshot_count"] == 1
    shadow_manifest["execution_boundary"]["orders_created"] = True
    with pytest.raises(MultiCikLiveError, match="MULTI_CIK_EXECUTION_BOUNDARY_FAILED"):
        finalize_live_bundle(
            gate=gate,
            aggregate_path=aggregate_path,
            aggregate_manifest=manifest,
            shadow_manifest=shadow_manifest,
        )


def test_workflow_locks_in_m17_regression_fixes():
    workflow = Path(".github/workflows/authorized-multi-cik-sec-shadow.yml").read_text(encoding="utf-8")
    assert "find runtime/live-multi-cik-sec -type f -name 'CIK*.json'" in workflow
    assert "database/universe-v1.0.csv" in workflow
    assert "data/universe-v1.0.csv" not in workflow
    assert "WINNER_TILT_SEC_EDGAR_MAX_TOTAL_REQUESTS: \"3\"" in workflow
    assert "AUTHORIZED_MULTI_CIK_SEC_SHADOW_RESEARCH_ONLY" in workflow
