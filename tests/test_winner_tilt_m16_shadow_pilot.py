import hashlib
import json
from pathlib import Path

import pytest

from winner_tilt.shadow_pilot import ShadowPilotError, run_shadow_pilot


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _prepare(tmp_path: Path):
    files = {}
    for name in ("snapshot.json", "ids.csv", "features.json", "scoring.json", "portfolio.json", "universe.csv"):
        path = tmp_path / name
        path.write_text("{}" if name.endswith(".json") else "header\n", encoding="utf-8")
        files[name] = name
    return files


def _vintage():
    return {
        "vintages": [{
            "information_cutoff": "2026-02-01T00:00:00Z",
            "scoring_configuration_sha256": "score-config",
            "certification": {"status": "CERTIFIED"},
            "lineage": [{"kind": "source", "sha256": "a" * 64}],
            "results": [{
                "security_id": "WT-0005", "ticker": "AAPL", "overall_rank": 1,
                "total_score": 88.0, "eligible": True, "available_at": "2026-01-31T12:00:00Z",
            }],
        }]
    }


def _shadow():
    portfolio = {
        "as_of_date": "2026-02-01",
        "holdings": [{"security_id": "WT-0005", "ticker": "AAPL", "portfolio_rank": 1, "weight": 1.0, "decision": "HOLD"}],
        "reserves": [],
        "dca_allocation": {"WT-0005": 1000.0},
        "exits": [],
        "portfolio_summary": {"one_way_turnover": 0.0},
    }
    return {
        "engine_version": "1.0.0",
        "mode": "SHADOW_RESEARCH_ONLY",
        "as_of_date": "2026-02-01",
        "certification": {"status": "CERTIFIED", "cutoff": "2026-02-01T00:00:00Z"},
        "portfolio": portfolio,
        "lineage": {
            "certified_vintage_sha256": "a" * 64,
            "portfolio_config_sha256": "b" * 64,
            "universe_sha256": "c" * 64,
            "portfolio_output_sha256": _hash(portfolio),
        },
        "execution_boundary": {
            "broker_connected": False, "orders_created": False, "orders_executed": False,
            "automatic_dca": False, "automatic_exits": False,
        },
        "output_sha256": "d" * 64,
    }


def test_end_to_end_orchestrator_emits_manifest_and_four_artifacts(tmp_path):
    paths = _prepare(tmp_path)
    manifest = run_shadow_pilot(
        root=tmp_path,
        snapshot_path=paths["snapshot.json"], identifier_registry_path=paths["ids.csv"],
        feature_definitions_path=paths["features.json"], scoring_config_path=paths["scoring.json"],
        portfolio_config_path=paths["portfolio.json"], universe_path=paths["universe.csv"],
        output_dir="runs", information_cutoff="2026-02-01T00:00:00Z",
        as_of_date="2026-02-01", decision_timestamp_utc="2026-02-01T01:00:00Z",
        run_id="m16-test", sec_to_score_runner=lambda **_: _vintage(),
        shadow_portfolio_runner=lambda **_: _shadow(),
    )
    assert manifest["status"] == "COMPLETED_SHADOW_RESEARCH_ONLY"
    assert manifest["live_sec_fetch_performed"] is False
    assert manifest["broker_integration_enabled"] is False
    assert len(manifest["artifacts"]) == 4
    assert all((tmp_path / path).is_file() for path in manifest["artifacts"].values())
    assert (tmp_path / "runs/m16-test/run-manifest.json").is_file()
    dashboard = json.loads((tmp_path / manifest["artifacts"]["dashboard_shadow_view"]).read_text())
    assert dashboard["status"]["orders_enabled"] is False
    assert dashboard["audit"]["validation_status"] == "SHADOW_CERTIFIED_RESEARCH_ONLY"


def test_output_is_deterministic_across_distinct_roots(tmp_path):
    manifests = []
    for folder in ("a", "b"):
        root = tmp_path / folder
        root.mkdir()
        paths = _prepare(root)
        manifests.append(run_shadow_pilot(
            root=root, snapshot_path=paths["snapshot.json"], identifier_registry_path=paths["ids.csv"],
            feature_definitions_path=paths["features.json"], scoring_config_path=paths["scoring.json"],
            portfolio_config_path=paths["portfolio.json"], universe_path=paths["universe.csv"],
            output_dir="runs", information_cutoff="2026-02-01T00:00:00Z", as_of_date="2026-02-01",
            decision_timestamp_utc="2026-02-01T01:00:00Z", run_id="same-run",
            sec_to_score_runner=lambda **_: _vintage(), shadow_portfolio_runner=lambda **_: _shadow(),
        ))
    assert manifests[0] == manifests[1]


def test_path_escape_is_blocked(tmp_path):
    with pytest.raises(ShadowPilotError, match="SHADOW_PILOT_SNAPSHOT_PATH_INVALID"):
        run_shadow_pilot(
            root=tmp_path, snapshot_path="../snapshot.json", identifier_registry_path="ids.csv",
            feature_definitions_path="features.json", scoring_config_path="scoring.json",
            portfolio_config_path="portfolio.json", universe_path="universe.csv", output_dir="runs",
            information_cutoff="2026-02-01T00:00:00Z", as_of_date="2026-02-01",
            decision_timestamp_utc="2026-02-01T01:00:00Z", run_id="bad",
        )


def test_executable_flag_is_blocked(tmp_path):
    paths = _prepare(tmp_path)
    shadow = _shadow()
    shadow["execution_boundary"]["orders_created"] = True
    with pytest.raises(ShadowPilotError, match="SHADOW_PILOT_EXECUTION_BOUNDARY_FAILED"):
        run_shadow_pilot(
            root=tmp_path, snapshot_path=paths["snapshot.json"], identifier_registry_path=paths["ids.csv"],
            feature_definitions_path=paths["features.json"], scoring_config_path=paths["scoring.json"],
            portfolio_config_path=paths["portfolio.json"], universe_path=paths["universe.csv"],
            output_dir="runs", information_cutoff="2026-02-01T00:00:00Z", as_of_date="2026-02-01",
            decision_timestamp_utc="2026-02-01T01:00:00Z", run_id="unsafe",
            sec_to_score_runner=lambda **_: _vintage(), shadow_portfolio_runner=lambda **_: shadow,
        )
