import hashlib
import json
from pathlib import Path

import pytest

from winner_tilt.dashboard import build_shadow_portfolio_view_model
from winner_tilt.decision_journal import JournalStore, validate_record
from winner_tilt.shadow_audit import (
    ShadowAuditError,
    append_shadow_journal_record,
    build_shadow_journal_record,
    validate_shadow_payload,
)


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def make_files(root: Path):
    portfolio = {
        "engine_version": "1.0.0",
        "as_of_date": "2026-06-30",
        "holdings": [{"security_id": "WT-0001", "ticker": "AAA", "portfolio_rank": 1, "weight": 1.0, "decision": "BUY"}],
        "reserves": [{"security_id": "WT-0002", "ticker": "BBB", "reserve_rank": 1, "decision": "WATCH"}],
        "exits": [],
        "dca_allocation": {"WT-0001": 1.0},
        "portfolio_summary": {"holdings_count": 1, "reserves_count": 1, "one_way_turnover": 0.0},
    }
    shadow = {
        "engine_version": "1.0.0",
        "mode": "SHADOW_RESEARCH_ONLY",
        "as_of_date": "2026-06-30",
        "certification": {"status": "CERTIFIED", "cutoff": "2026-06-29T00:00:00Z", "result_count": 2, "vintage_sha256": "a" * 64},
        "portfolio": portfolio,
        "lineage": {
            "certified_vintage_sha256": "b" * 64,
            "portfolio_config_sha256": "c" * 64,
            "universe_sha256": "d" * 64,
            "portfolio_output_sha256": canonical_hash(portfolio),
        },
        "execution_boundary": {
            "broker_connected": False,
            "orders_created": False,
            "orders_executed": False,
            "automatic_dca": False,
            "automatic_exits": False,
        },
    }
    shadow["output_sha256"] = canonical_hash(shadow)
    vintage = {
        "vintages": [{
            "information_cutoff": "2026-06-29T00:00:00Z",
            "generated_at": "2026-06-29T00:00:00Z",
            "certification": {"status": "CERTIFIED"},
            "lineage": [{"name": "source", "sha256": "e" * 64}],
            "results": [
                {"security_id": "WT-0001", "ticker": "AAA", "overall_rank": 1, "total_score": 90.0, "eligible": True, "available_at": "2026-06-28T00:00:00Z"},
                {"security_id": "WT-0002", "ticker": "BBB", "overall_rank": 2, "total_score": 80.0, "eligible": True, "available_at": "2026-06-28T00:00:00Z"},
            ],
        }]
    }
    (root / "reports").mkdir()
    (root / "config").mkdir()
    (root / "reports/shadow.json").write_text(json.dumps(shadow), encoding="utf-8")
    (root / "reports/vintage.json").write_text(json.dumps(vintage), encoding="utf-8")
    (root / "config/universe.csv").write_text("WT_ID,Ticker\nWT-0001,AAA\nWT-0002,BBB\n", encoding="utf-8")
    return shadow


def test_builds_valid_append_only_journal_and_dashboard_view(tmp_path, monkeypatch):
    shadow = make_files(tmp_path)
    record = build_shadow_journal_record(
        shadow_path="reports/shadow.json",
        vintage_path="reports/vintage.json",
        universe_path="config/universe.csv",
        root=tmp_path,
        decision_timestamp_utc="2026-06-30T12:00:00Z",
        run_id="M15-TEST",
    )
    validate_record(record)
    assert record["validation_status"] == "SHADOW_CERTIFIED_RESEARCH_ONLY"
    assert record["selected_holdings"][0]["security_id"] == "WT-0001"

    monkeypatch.chdir(tmp_path)
    append_shadow_journal_record(journal_path="reports/journal.jsonl", record=record)
    integrity = JournalStore("reports/journal.jsonl").verify_integrity()
    assert integrity["valid"] is True
    assert integrity["record_count"] == 1

    view = build_shadow_portfolio_view_model(shadow, record)
    assert view["status"]["dashboard_mode"] == "READ_ONLY_SHADOW_RESEARCH_ONLY"
    assert view["status"]["orders_enabled"] is False
    assert view["audit"]["immutable_record_hash"] == record["immutable_record_hash"]
    assert view["holdings"][0]["weight_pct"] == 100.0


def test_executable_shadow_payload_is_blocked(tmp_path):
    shadow = make_files(tmp_path)
    shadow["execution_boundary"]["orders_created"] = True
    with pytest.raises(ShadowAuditError, match="SHADOW_AUDIT_EXECUTABLE_FLAG_DETECTED"):
        validate_shadow_payload(shadow)


def test_portfolio_hash_tampering_is_blocked(tmp_path):
    shadow = make_files(tmp_path)
    shadow["portfolio"]["holdings"][0]["weight"] = 0.5
    with pytest.raises(ShadowAuditError, match="SHADOW_AUDIT_PORTFOLIO_HASH_MISMATCH"):
        validate_shadow_payload(shadow)


def test_duplicate_selection_is_blocked(tmp_path):
    shadow = make_files(tmp_path)
    shadow["portfolio"]["reserves"][0]["security_id"] = "WT-0001"
    shadow["lineage"]["portfolio_output_sha256"] = canonical_hash(shadow["portfolio"])
    with pytest.raises(ShadowAuditError, match="SHADOW_AUDIT_DUPLICATE_SELECTION"):
        validate_shadow_payload(shadow)


def test_record_is_deterministic(tmp_path):
    make_files(tmp_path)
    kwargs = dict(
        shadow_path="reports/shadow.json",
        vintage_path="reports/vintage.json",
        universe_path="config/universe.csv",
        root=tmp_path,
        decision_timestamp_utc="2026-06-30T12:00:00Z",
        run_id="M15-TEST",
    )
    assert build_shadow_journal_record(**kwargs) == build_shadow_journal_record(**kwargs)
