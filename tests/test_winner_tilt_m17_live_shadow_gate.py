import json
from pathlib import Path

import pytest

from winner_tilt.live_shadow_gate import (
    AUTHORIZATION_PHRASE,
    LiveShadowGateError,
    certify_bundle,
    select_single_snapshot,
    validate_authorization,
)


def registry(tmp_path: Path) -> Path:
    path = tmp_path / "ids.csv"
    path.write_text(
        "cik,security_id,ticker,status,effective_from,effective_to,source\n"
        "0000320193,WT-0005,AAPL,ACTIVE,2026-01-01,,test\n",
        encoding="utf-8",
    )
    return path


def test_authorization_requires_exact_phrase_and_active_registry_link(tmp_path):
    result = validate_authorization(
        cik="320193", authorization=AUTHORIZATION_PHRASE,
        identifier_registry_path=registry(tmp_path),
    )
    assert result["status"] == "AUTHORIZED_LIVE_FETCH"
    assert result["cik"] == "0000320193"
    assert result["security_id"] == "WT-0005"
    assert result["downstream_execution_enabled"] is False


def test_wrong_authorization_fails_closed(tmp_path):
    with pytest.raises(LiveShadowGateError, match="LIVE_SHADOW_AUTHORIZATION_REQUIRED"):
        validate_authorization(cik="0000320193", authorization="yes", identifier_registry_path=registry(tmp_path))


def test_unregistered_cik_fails_closed(tmp_path):
    with pytest.raises(LiveShadowGateError, match="LIVE_SHADOW_CIK_NOT_ACTIVE_AND_UNIQUE"):
        validate_authorization(
            cik="0000789019", authorization=AUTHORIZATION_PHRASE,
            identifier_registry_path=registry(tmp_path),
        )


def test_single_snapshot_is_required(tmp_path):
    directory = tmp_path / "snapshots"
    directory.mkdir()
    with pytest.raises(LiveShadowGateError, match="LIVE_SHADOW_SINGLE_SNAPSHOT_REQUIRED"):
        select_single_snapshot(directory)
    (directory / "one.json").write_text("{}", encoding="utf-8")
    assert select_single_snapshot(directory).name == "one.json"
    (directory / "two.json").write_text("{}", encoding="utf-8")
    with pytest.raises(LiveShadowGateError, match="LIVE_SHADOW_SINGLE_SNAPSHOT_REQUIRED"):
        select_single_snapshot(directory)


def test_bundle_certification_hashes_artifacts_and_preserves_execution_boundary(tmp_path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text('{"rows": []}', encoding="utf-8")
    manifest_path = tmp_path / "run-manifest.json"
    manifest_path.write_text(json.dumps({
        "execution_boundary": {
            "broker_connected": False,
            "orders_created": False,
            "orders_executed": False,
            "automatic_dca": False,
            "automatic_exits": False,
        },
        "broker_integration_enabled": False,
    }), encoding="utf-8")
    gate = {
        "status": "AUTHORIZED_LIVE_FETCH",
        "research_only": True,
        "cik": "0000320193",
    }
    result = certify_bundle(gate=gate, snapshot_path=snapshot, shadow_manifest_path=manifest_path)
    assert result["status"] == "COMPLETED_AUTHORIZED_LIVE_SHADOW_RESEARCH_ONLY"
    assert len(result["snapshot_sha256"]) == 64
    assert result["orders_created"] is False
    assert result["orders_executed"] is False


def test_bundle_blocks_executable_flags(tmp_path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text("{}", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "execution_boundary": {"orders_created": True},
        "broker_integration_enabled": False,
    }), encoding="utf-8")
    with pytest.raises(LiveShadowGateError, match="LIVE_SHADOW_EXECUTION_BOUNDARY_FAILED"):
        certify_bundle(
            gate={"status": "AUTHORIZED_LIVE_FETCH", "research_only": True},
            snapshot_path=snapshot,
            shadow_manifest_path=manifest,
        )
