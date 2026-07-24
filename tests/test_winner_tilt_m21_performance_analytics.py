import json
from pathlib import Path

import pytest

from winner_tilt.performance_analytics import (
    AUTHORIZATION_PHRASE,
    PerformanceAnalyticsError,
    _metrics,
    certify_performance,
)


def write_inputs(tmp_path: Path, *, validation_status="PRODUCTION_VALID"):
    replay = {
        "status": "CERTIFIED_HISTORICAL_REPLAY_RESEARCH_ONLY",
        "periods": [
            {"information_cutoff": "2025-01-31T23:59:59Z", "status": "PORTFOLIO_READY"},
            {"information_cutoff": "2025-02-28T23:59:59Z", "status": "INSUFFICIENT_COVERAGE"},
            {"information_cutoff": "2025-03-31T23:59:59Z", "status": "PORTFOLIO_READY"},
        ],
        "execution_boundary": {
            "broker_connected": False,
            "orders_created": False,
            "orders_executed": False,
            "automatic_dca": False,
            "automatic_exits": False,
        },
    }
    values = [100.0, 105.0, 102.0, 110.0]
    benchmark = [100.0, 102.0, 103.0, 106.0]
    backtest = {
        "validation_status": validation_status,
        "configuration_sha256": "a" * 64,
        "data_manifest_sha256": "b" * 64,
        "metrics": _metrics(values),
        "benchmark_metrics": _metrics(benchmark),
        "turnover": {"cumulative_one_way": 0.75},
        "transaction_costs": 12.5,
        "equity_curve": [
            {"date": f"2025-01-0{i + 1}", "portfolio_value": value, "benchmark_value": benchmark[i], "cash": 0.0}
            for i, value in enumerate(values)
        ],
    }
    replay_path = tmp_path / "replay.json"
    backtest_path = tmp_path / "backtest.json"
    replay_path.write_text(json.dumps(replay), encoding="utf-8")
    backtest_path.write_text(json.dumps(backtest), encoding="utf-8")
    return replay_path, backtest_path, backtest


def test_certifies_production_valid_performance(tmp_path):
    replay_path, backtest_path, _ = write_inputs(tmp_path)
    result = certify_performance(
        replay_manifest_path=replay_path,
        backtest_output_path=backtest_path,
        authorization=AUTHORIZATION_PHRASE,
    )
    assert result["status"] == "PERFORMANCE_CERTIFIED"
    assert result["readiness_summary"] == {
        "period_count": 3,
        "portfolio_ready_period_count": 2,
        "insufficient_coverage_period_count": 1,
        "ready_participation_rate": 2 / 3,
    }
    assert result["metrics"]["total_return"] == pytest.approx(0.10)
    assert result["relative_metrics"]["ending_value_spread"] == pytest.approx(4.0)
    assert all(value is False for value in result["execution_boundary"].values())


def test_validation_only_never_claims_certification(tmp_path):
    replay_path, backtest_path, _ = write_inputs(tmp_path, validation_status="VALIDATION_ONLY")
    result = certify_performance(
        replay_manifest_path=replay_path,
        backtest_output_path=backtest_path,
        authorization=AUTHORIZATION_PHRASE,
    )
    assert result["status"] == "VALIDATION_ONLY"


def test_metric_tamper_fails_closed(tmp_path):
    replay_path, backtest_path, backtest = write_inputs(tmp_path)
    backtest["metrics"]["total_return"] = 999
    backtest_path.write_text(json.dumps(backtest), encoding="utf-8")
    with pytest.raises(PerformanceAnalyticsError, match="PERFORMANCE_METRIC_MISMATCH:total_return"):
        certify_performance(
            replay_manifest_path=replay_path,
            backtest_output_path=backtest_path,
            authorization=AUTHORIZATION_PHRASE,
        )


def test_execution_boundary_and_authorization_fail_closed(tmp_path):
    replay_path, backtest_path, _ = write_inputs(tmp_path)
    replay = json.loads(replay_path.read_text())
    replay["execution_boundary"]["orders_created"] = True
    replay_path.write_text(json.dumps(replay))
    with pytest.raises(PerformanceAnalyticsError, match="PERFORMANCE_EXECUTION_BOUNDARY_FAILED"):
        certify_performance(
            replay_manifest_path=replay_path,
            backtest_output_path=backtest_path,
            authorization=AUTHORIZATION_PHRASE,
        )
    with pytest.raises(PerformanceAnalyticsError, match="PERFORMANCE_AUTHORIZATION_REQUIRED"):
        certify_performance(
            replay_manifest_path=replay_path,
            backtest_output_path=backtest_path,
            authorization="wrong",
        )


def test_workflow_preserves_historical_regression_contracts():
    workflow = Path(".github/workflows/performance-analytics-certification.yml").read_text(encoding="utf-8")
    assert "type: choice" in workflow
    assert "AUTHORIZE_PERFORMANCE_ANALYTICS_RESEARCH_ONLY" in workflow
    assert "performance-analytics-output.log" in workflow
    assert "if: always()" in workflow
    assert "historical-replay-manifest.json" in workflow
