import hashlib
import json
from pathlib import Path

import pytest

from winner_tilt.portfolio_readiness import PortfolioReadinessError, certify_readiness


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bundle(tmp_path: Path, *, insufficient: bool):
    run_dir = tmp_path / "runs" / "r1"
    boundary = {
        "broker_connected": False,
        "orders_created": False,
        "orders_executed": False,
        "automatic_dca": False,
        "automatic_exits": False,
    }
    portfolio = {
        "construction_status": "INSUFFICIENT_COVERAGE_RESEARCH_ONLY" if insufficient else "PORTFOLIO_CONSTRUCTED",
        "holdings": [] if insufficient else [{"security_id": f"H{i}"} for i in range(15)],
        "reserves": [] if insufficient else [{"security_id": f"R{i}"} for i in range(15)],
        "portfolio_summary": {
            "eligible_candidate_count": 3 if insufficient else 30,
            "required_candidate_count": 30,
        },
    }
    values = {
        "certified_shadow_portfolio": {"portfolio": portfolio, "execution_boundary": boundary},
        "certified_score_vintage": {"vintages": [{"certification": {"status": "CERTIFIED"}}]},
        "decision_journal_record": {"status": "VALIDATED"},
        "dashboard_shadow_view": {"mode": "READ_ONLY"},
    }
    artifacts = {}
    hashes = {}
    for name, value in values.items():
        path = run_dir / f"{name}.json"
        write_json(path, value)
        artifacts[name] = str(path.relative_to(tmp_path))
        hashes[name] = sha(path)
    manifest = {
        "status": "COMPLETED_SHADOW_RESEARCH_ONLY",
        "run_id": "r1",
        "as_of_date": "2026-07-24",
        "artifacts": artifacts,
        "artifact_sha256": hashes,
        "execution_boundary": boundary,
        "broker_integration_enabled": False,
    }
    manifest_path = run_dir / "run-manifest.json"
    write_json(manifest_path, manifest)
    config_path = tmp_path / "portfolio.json"
    write_json(config_path, {"portfolio": {"holdings_count": 15, "reserves_count": 15}})
    return manifest_path, config_path


def test_insufficient_coverage_is_certified_research_outcome(tmp_path):
    manifest, config = bundle(tmp_path, insufficient=True)
    assessment, package = certify_readiness(root=tmp_path, run_manifest_path=manifest, portfolio_config_path=config)
    assert assessment["status"] == "INSUFFICIENT_COVERAGE"
    assert assessment["coverage"]["candidate_shortfall"] == 27
    assert package["research_only"] is True
    assert package["portfolio_readiness"] == "INSUFFICIENT_COVERAGE"


def test_full_frozen_counts_are_portfolio_ready(tmp_path):
    manifest, config = bundle(tmp_path, insufficient=False)
    assessment, package = certify_readiness(root=tmp_path, run_manifest_path=manifest, portfolio_config_path=config)
    assert assessment["status"] == "PORTFOLIO_READY"
    assert assessment["coverage"]["selected_holdings_count"] == 15
    assert assessment["coverage"]["selected_reserves_count"] == 15
    assert package["portfolio_readiness"] == "PORTFOLIO_READY"


def test_artifact_hash_mismatch_fails_closed(tmp_path):
    manifest, config = bundle(tmp_path, insufficient=True)
    payload = json.loads(manifest.read_text())
    target = tmp_path / payload["artifacts"]["certified_score_vintage"]
    target.write_text("{}", encoding="utf-8")
    with pytest.raises(PortfolioReadinessError, match="READINESS_ARTIFACT_HASH_MISMATCH"):
        certify_readiness(root=tmp_path, run_manifest_path=manifest, portfolio_config_path=config)


def test_executable_boundary_fails_closed(tmp_path):
    manifest, config = bundle(tmp_path, insufficient=True)
    payload = json.loads(manifest.read_text())
    payload["execution_boundary"]["orders_created"] = True
    write_json(manifest, payload)
    with pytest.raises(PortfolioReadinessError, match="READINESS_EXECUTION_BOUNDARY_FAILED"):
        certify_readiness(root=tmp_path, run_manifest_path=manifest, portfolio_config_path=config)


def test_m17_m18_regression_contracts_remain_in_live_workflow():
    workflow = Path(".github/workflows/authorized-multi-cik-sec-shadow.yml").read_text(encoding="utf-8")
    assert "database/universe-v1.0.csv" in workflow
    assert "find runtime/live-multi-cik-sec -type f -name 'CIK*.json'" in workflow
    assert "type: choice" in workflow
    assert "authorization-gate-output.log" in workflow
    assert "portfolio-readiness-assessment.json" in workflow
    assert "investment-committee-research-package.json" in workflow
    assert "portfolio-readiness-output.log" in workflow
