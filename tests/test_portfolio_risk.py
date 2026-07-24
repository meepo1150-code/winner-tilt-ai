import json
from pathlib import Path

import pytest

from winner_tilt.portfolio_risk import AUTHORIZATION, certify


def _write(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def _fixtures(tmp_path: Path):
    portfolio = {
        "positions": [
            {"symbol": "AAA", "sector": "Technology", "weight": 0.4},
            {"symbol": "BBB", "sector": "Healthcare", "weight": 0.35},
            {"symbol": "CCC", "sector": "Technology", "weight": 0.25},
        ]
    }
    curve = [
        {"date": "2025-01-01", "portfolio_value": 100.0, "benchmark_value": 100.0},
        {"date": "2025-01-02", "portfolio_value": 102.0, "benchmark_value": 101.0},
        {"date": "2025-01-03", "portfolio_value": 101.0, "benchmark_value": 101.5},
        {"date": "2025-01-04", "portfolio_value": 104.0, "benchmark_value": 102.0},
    ]
    performance = {
        "status": "PERFORMANCE_CERTIFIED",
        "equity_curve": curve,
        "execution_boundary": {
            "broker_connected": False,
            "orders_created": False,
            "orders_executed": False,
            "automatic_dca": False,
            "automatic_exits": False,
        },
    }
    replay = {
        "status": "CERTIFIED_HISTORICAL_REPLAY_RESEARCH_ONLY",
        "period_count": 3,
        "portfolio_ready_period_count": 2,
        "insufficient_coverage_period_count": 1,
    }
    return (
        _write(tmp_path / "portfolio.json", portfolio),
        _write(tmp_path / "performance.json", performance),
        _write(tmp_path / "replay.json", replay),
    )


def test_certifies_deterministically(tmp_path):
    portfolio, performance, replay = _fixtures(tmp_path)
    report = certify(portfolio, performance, replay, AUTHORIZATION)
    assert report["status"] == "PORTFOLIO_RISK_CERTIFIED_RESEARCH_ONLY"
    assert report["position_count"] == 3
    assert report["sector_count"] == 2
    assert report["concentration"]["hhi"] == pytest.approx(0.345)
    assert report["concentration"]["maximum_position_weight"] == 0.4
    assert report["readiness_summary"]["insufficient_coverage_preserved"] is True
    assert not any(report["execution_boundary"].values())


def test_rejects_invalid_authorization(tmp_path):
    portfolio, performance, replay = _fixtures(tmp_path)
    with pytest.raises(ValueError, match="authorization"):
        certify(portfolio, performance, replay, "NO")


def test_rejects_bad_weight_sum(tmp_path):
    portfolio, performance, replay = _fixtures(tmp_path)
    data = json.loads(portfolio.read_text())
    data["positions"][0]["weight"] = 0.3
    portfolio.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="sum"):
        certify(portfolio, performance, replay, AUTHORIZATION)


def test_rejects_uncertified_performance(tmp_path):
    portfolio, performance, replay = _fixtures(tmp_path)
    data = json.loads(performance.read_text())
    data["status"] = "VALIDATION_ONLY"
    performance.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="not certified"):
        certify(portfolio, performance, replay, AUTHORIZATION)


def test_rejects_unordered_curve(tmp_path):
    portfolio, performance, replay = _fixtures(tmp_path)
    data = json.loads(performance.read_text())
    data["equity_curve"][1]["date"] = "2024-01-01"
    performance.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="ordered"):
        certify(portfolio, performance, replay, AUTHORIZATION)
