import json
from pathlib import Path

import pytest

from winner_tilt.factor_attribution import (
    AUTHORIZATION_PHRASE,
    FactorAttributionError,
    certify_attribution,
    discover_inputs,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _fixtures(tmp_path: Path):
    boundary = {
        "broker_connected": False,
        "orders_created": False,
        "orders_executed": False,
        "automatic_dca": False,
        "automatic_exits": False,
    }
    replay = _write(tmp_path / "replay.json", {
        "status": "CERTIFIED_HISTORICAL_REPLAY_RESEARCH_ONLY",
        "portfolio_ready_period_count": 1,
        "insufficient_coverage_period_count": 1,
        "periods": [
            {"information_cutoff": "2025-01-31T23:59:59Z", "status": "PORTFOLIO_READY"},
            {"information_cutoff": "2025-02-28T23:59:59Z", "status": "INSUFFICIENT_COVERAGE"},
        ],
        "execution_boundary": boundary,
    })
    performance = _write(tmp_path / "performance.json", {
        "status": "PERFORMANCE_CERTIFIED",
        "execution_boundary": boundary,
    })
    scores = tmp_path / "scores"
    _write(scores / "2025" / "one.json", {
        "information_cutoff": "2025-01-31T23:59:59Z",
        "results": [{
            "security_id": "AAA", "sector": "Technology", "eligible": True,
            "base_score": 50.0, "total_score": 72.0,
            "factor_contributions": {"growth": 15.0, "quality": 10.0, "risk_penalty": -3.0},
        }],
    })
    _write(scores / "2025" / "two.json", {
        "information_cutoff": "2025-02-28T23:59:59Z",
        "results": [{
            "security_id": "BBB", "sector": "Health Care", "eligible": False,
            "base_score": 50.0, "total_score": 54.0,
            "factor_contributions": {"growth": 6.0, "quality": 2.0, "risk_penalty": -4.0},
        }],
    })
    return scores, replay, performance


def test_recursive_discovery_and_certification(tmp_path):
    scores, replay, performance = _fixtures(tmp_path)
    assert len(discover_inputs(scores)) == 2
    report = certify_attribution(
        score_input_path=scores,
        replay_manifest_path=replay,
        performance_certification_path=performance,
        authorization=AUTHORIZATION_PHRASE,
    )
    assert report["status"] == "FACTOR_ATTRIBUTION_CERTIFIED_RESEARCH_ONLY"
    assert report["record_count"] == 2
    assert report["factor_count"] == 3
    assert report["aggregate_attribution"]["by_factor"]["growth"] == 21.0
    assert report["readiness_summary"]["insufficient_coverage_preserved_as_research_only"] is True
    assert not any(report["execution_boundary"].values())


def test_wrong_authorization_fails_closed(tmp_path):
    scores, replay, performance = _fixtures(tmp_path)
    with pytest.raises(FactorAttributionError, match="AUTHORIZATION_REQUIRED"):
        certify_attribution(score_input_path=scores, replay_manifest_path=replay,
                            performance_certification_path=performance, authorization="wrong")


def test_tampered_total_score_fails(tmp_path):
    scores, replay, performance = _fixtures(tmp_path)
    path = scores / "2025" / "one.json"
    payload = json.loads(path.read_text())
    payload["results"][0]["total_score"] = 99.0
    _write(path, payload)
    with pytest.raises(FactorAttributionError, match="SCORE_MISMATCH"):
        certify_attribution(score_input_path=scores, replay_manifest_path=replay,
                            performance_certification_path=performance,
                            authorization=AUTHORIZATION_PHRASE)


def test_uncertified_performance_fails(tmp_path):
    scores, replay, performance = _fixtures(tmp_path)
    payload = json.loads(performance.read_text())
    payload["status"] = "VALIDATION_ONLY"
    _write(performance, payload)
    with pytest.raises(FactorAttributionError, match="PERFORMANCE_NOT_CERTIFIED"):
        certify_attribution(score_input_path=scores, replay_manifest_path=replay,
                            performance_certification_path=performance,
                            authorization=AUTHORIZATION_PHRASE)


def test_execution_boundary_violation_fails(tmp_path):
    scores, replay, performance = _fixtures(tmp_path)
    payload = json.loads(replay.read_text())
    payload["execution_boundary"]["orders_created"] = True
    _write(replay, payload)
    with pytest.raises(FactorAttributionError, match="EXECUTION_BOUNDARY_VIOLATION"):
        certify_attribution(score_input_path=scores, replay_manifest_path=replay,
                            performance_certification_path=performance,
                            authorization=AUTHORIZATION_PHRASE)
