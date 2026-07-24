import json
from pathlib import Path

import pytest

from winner_tilt.historical_replay import (
    AUTHORIZATION_PHRASE,
    HistoricalReplayError,
    certify_replay,
)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def config(path: Path):
    write_json(path, {"portfolio": {"holdings_count": 2, "reserves_count": 1}})


def vintage(cutoff: str, eligible: int, *, future=False):
    rows = []
    for index in range(3):
        rows.append({
            "security_id": f"WT-{index:04d}",
            "eligible": index < eligible,
            "total_score": 80 - index if index < eligible else None,
            "available_at": "2030-01-01T00:00:00Z" if future and index == 0 else cutoff,
        })
    return {
        "vintages": [{
            "information_cutoff": cutoff,
            "generated_at": cutoff,
            "certification": {"status": "CERTIFIED"},
            "results": rows,
        }]
    }


def test_replay_classifies_ready_and_insufficient_periods(tmp_path):
    cfg = tmp_path / "portfolio.json"
    config(cfg)
    root = tmp_path / "vintages"
    write_json(root / "nested" / "v1.json", vintage("2025-01-31T00:00:00Z", 3))
    write_json(root / "v2.json", vintage("2025-02-28T00:00:00Z", 1))
    result = certify_replay(vintage_path=root, portfolio_config_path=cfg, authorization=AUTHORIZATION_PHRASE)
    assert result["status"] == "CERTIFIED_HISTORICAL_REPLAY_RESEARCH_ONLY"
    assert result["period_count"] == 2
    assert result["portfolio_ready_period_count"] == 1
    assert result["insufficient_coverage_period_count"] == 1
    assert [item["status"] for item in result["periods"]] == ["PORTFOLIO_READY", "INSUFFICIENT_COVERAGE"]
    assert all(value is False for value in result["execution_boundary"].values())


def test_authorization_fails_closed(tmp_path):
    cfg = tmp_path / "portfolio.json"
    config(cfg)
    path = tmp_path / "vintage.json"
    write_json(path, vintage("2025-01-31T00:00:00Z", 3))
    with pytest.raises(HistoricalReplayError, match="HISTORICAL_REPLAY_AUTHORIZATION_REQUIRED"):
        certify_replay(vintage_path=path, portfolio_config_path=cfg, authorization="wrong")


def test_lookahead_is_blocked(tmp_path):
    cfg = tmp_path / "portfolio.json"
    config(cfg)
    path = tmp_path / "vintage.json"
    write_json(path, vintage("2025-01-31T00:00:00Z", 3, future=True))
    with pytest.raises(HistoricalReplayError, match="HISTORICAL_REPLAY_LOOKAHEAD"):
        certify_replay(vintage_path=path, portfolio_config_path=cfg, authorization=AUTHORIZATION_PHRASE)


def test_duplicate_cutoff_is_blocked(tmp_path):
    cfg = tmp_path / "portfolio.json"
    config(cfg)
    root = tmp_path / "vintages"
    write_json(root / "a.json", vintage("2025-01-31T00:00:00Z", 3))
    write_json(root / "nested" / "b.json", vintage("2025-01-31T00:00:00Z", 2))
    with pytest.raises(HistoricalReplayError, match="HISTORICAL_REPLAY_DUPLICATE_CUTOFF"):
        certify_replay(vintage_path=root, portfolio_config_path=cfg, authorization=AUTHORIZATION_PHRASE)


def test_workflow_preserves_historical_regression_contracts():
    workflow = Path(".github/workflows/historical-replay-certification.yml").read_text(encoding="utf-8")
    assert "type: choice" in workflow
    assert "AUTHORIZE_HISTORICAL_REPLAY_RESEARCH_ONLY" in workflow
    assert "database/universe-v1.0.csv" in workflow
    assert "historical-replay-output.log" in workflow
    assert "if-no-files-found: error" in workflow
