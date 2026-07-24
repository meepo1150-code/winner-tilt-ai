"""Deterministic walk-forward performance analytics certification."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

ENGINE_VERSION = "1.0.0"
AUTHORIZATION_PHRASE = "AUTHORIZE_PERFORMANCE_ANALYTICS_RESEARCH_ONLY"
TRADING_DAYS = 252
TOLERANCE = 1e-10


class PerformanceAnalyticsError(ValueError):
    """Raised when performance analytics certification fails closed."""


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite(value: Any, code: str, *, allow_none: bool = False) -> float | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise PerformanceAnalyticsError(code)
    return float(value)


def _metrics(values: list[float], risk_free_rate: float = 0.0) -> dict[str, float | None]:
    if len(values) < 2:
        raise PerformanceAnalyticsError("PERFORMANCE_EQUITY_CURVE_TOO_SHORT")
    if any(value <= 0 or not math.isfinite(value) for value in values):
        raise PerformanceAnalyticsError("PERFORMANCE_EQUITY_VALUE_INVALID")
    returns = [values[index] / values[index - 1] - 1 for index in range(1, len(values))]
    years = max((len(values) - 1) / TRADING_DAYS, 1 / TRADING_DAYS)
    total_return = values[-1] / values[0] - 1
    cagr = (values[-1] / values[0]) ** (1 / years) - 1
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / max(1, len(returns) - 1)
    volatility = math.sqrt(variance) * math.sqrt(TRADING_DAYS)
    downside = [min(0.0, item) for item in returns]
    downside_volatility = math.sqrt(sum(item * item for item in downside) / max(1, len(downside))) * math.sqrt(TRADING_DAYS)
    annualized_return = mean * TRADING_DAYS
    excess = annualized_return - risk_free_rate
    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value / peak - 1)
    return {
        "total_return": total_return,
        "cagr": cagr,
        "annualized_return": annualized_return,
        "annualized_volatility": volatility,
        "sharpe": excess / volatility if volatility else None,
        "sortino": excess / downside_volatility if downside_volatility else None,
        "max_drawdown": max_drawdown,
    }


def _assert_close(expected: float | None, actual: Any, code: str) -> None:
    parsed = _finite(actual, code, allow_none=True)
    if expected is None or parsed is None:
        if expected is not parsed:
            raise PerformanceAnalyticsError(code)
        return
    if not math.isclose(expected, parsed, rel_tol=TOLERANCE, abs_tol=TOLERANCE):
        raise PerformanceAnalyticsError(code)


def certify_performance(*, replay_manifest_path: str | Path, backtest_output_path: str | Path,
                        authorization: str) -> dict[str, Any]:
    if authorization != AUTHORIZATION_PHRASE:
        raise PerformanceAnalyticsError("PERFORMANCE_AUTHORIZATION_REQUIRED")
    replay_path = Path(replay_manifest_path)
    backtest_path = Path(backtest_output_path)
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    backtest = json.loads(backtest_path.read_text(encoding="utf-8"))

    if replay.get("status") != "CERTIFIED_HISTORICAL_REPLAY_RESEARCH_ONLY":
        raise PerformanceAnalyticsError("PERFORMANCE_REPLAY_NOT_CERTIFIED")
    boundary = replay.get("execution_boundary")
    if not isinstance(boundary, Mapping) or any(value is not False for value in boundary.values()):
        raise PerformanceAnalyticsError("PERFORMANCE_EXECUTION_BOUNDARY_FAILED")
    periods = replay.get("periods")
    if not isinstance(periods, list) or not periods:
        raise PerformanceAnalyticsError("PERFORMANCE_REPLAY_PERIODS_REQUIRED")
    cutoffs = [period.get("information_cutoff") for period in periods]
    if any(not isinstance(item, str) or not item for item in cutoffs) or cutoffs != sorted(cutoffs) or len(cutoffs) != len(set(cutoffs)):
        raise PerformanceAnalyticsError("PERFORMANCE_REPLAY_ORDER_INVALID")

    validation_status = backtest.get("validation_status")
    if validation_status not in {"PRODUCTION_VALID", "VALIDATION_ONLY"}:
        raise PerformanceAnalyticsError("PERFORMANCE_BACKTEST_STATUS_INVALID")
    curve = backtest.get("equity_curve")
    if not isinstance(curve, list) or len(curve) < 2:
        raise PerformanceAnalyticsError("PERFORMANCE_EQUITY_CURVE_REQUIRED")
    dates: list[str] = []
    portfolio_values: list[float] = []
    benchmark_values: list[float] = []
    benchmark_complete = True
    previous_date: str | None = None
    drawdown_series: list[dict[str, Any]] = []
    peak = 0.0
    for row in curve:
        if not isinstance(row, Mapping):
            raise PerformanceAnalyticsError("PERFORMANCE_EQUITY_ROW_INVALID")
        date = row.get("date")
        if not isinstance(date, str) or not date or (previous_date is not None and date <= previous_date):
            raise PerformanceAnalyticsError("PERFORMANCE_EQUITY_DATE_ORDER_INVALID")
        previous_date = date
        dates.append(date)
        value = _finite(row.get("portfolio_value"), "PERFORMANCE_EQUITY_VALUE_INVALID")
        assert value is not None
        portfolio_values.append(value)
        peak = max(peak, value)
        drawdown_series.append({"date": date, "drawdown": value / peak - 1})
        benchmark = row.get("benchmark_value")
        if benchmark is None:
            benchmark_complete = False
        else:
            parsed = _finite(benchmark, "PERFORMANCE_BENCHMARK_VALUE_INVALID")
            assert parsed is not None
            benchmark_values.append(parsed)

    risk_free_rate = _finite(backtest.get("risk_free_rate", 0.0), "PERFORMANCE_RISK_FREE_RATE_INVALID") or 0.0
    computed = _metrics(portfolio_values, risk_free_rate)
    supplied = backtest.get("metrics")
    if not isinstance(supplied, Mapping):
        raise PerformanceAnalyticsError("PERFORMANCE_METRICS_REQUIRED")
    for key, expected in computed.items():
        _assert_close(expected, supplied.get(key), "PERFORMANCE_METRIC_MISMATCH:" + key)

    benchmark_metrics: dict[str, float | None] = {}
    if benchmark_complete:
        if len(benchmark_values) != len(portfolio_values):
            raise PerformanceAnalyticsError("PERFORMANCE_BENCHMARK_ALIGNMENT_INVALID")
        benchmark_metrics = _metrics(benchmark_values, risk_free_rate)
        supplied_benchmark = backtest.get("benchmark_metrics")
        if not isinstance(supplied_benchmark, Mapping):
            raise PerformanceAnalyticsError("PERFORMANCE_BENCHMARK_METRICS_REQUIRED")
        for key, expected in benchmark_metrics.items():
            _assert_close(expected, supplied_benchmark.get(key), "PERFORMANCE_BENCHMARK_METRIC_MISMATCH:" + key)

    turnover = backtest.get("turnover")
    if not isinstance(turnover, Mapping):
        raise PerformanceAnalyticsError("PERFORMANCE_TURNOVER_REQUIRED")
    cumulative_turnover = _finite(turnover.get("cumulative_one_way"), "PERFORMANCE_TURNOVER_INVALID")
    transaction_costs = _finite(backtest.get("transaction_costs"), "PERFORMANCE_TRANSACTION_COST_INVALID")
    assert cumulative_turnover is not None and transaction_costs is not None
    if cumulative_turnover < 0 or transaction_costs < 0:
        raise PerformanceAnalyticsError("PERFORMANCE_COST_OR_TURNOVER_NEGATIVE")

    ready = sum(period.get("status") == "PORTFOLIO_READY" for period in periods)
    insufficient = sum(period.get("status") == "INSUFFICIENT_COVERAGE" for period in periods)
    if ready + insufficient != len(periods):
        raise PerformanceAnalyticsError("PERFORMANCE_REPLAY_PERIOD_STATUS_INVALID")
    certification_status = "PERFORMANCE_CERTIFIED" if validation_status == "PRODUCTION_VALID" else "VALIDATION_ONLY"
    relative = {}
    if benchmark_metrics:
        relative = {
            "cagr_spread": computed["cagr"] - benchmark_metrics["cagr"],
            "ending_value_spread": portfolio_values[-1] - benchmark_values[-1],
        }
    result = {
        "engine_version": ENGINE_VERSION,
        "status": certification_status,
        "research_only": True,
        "backtest_validation_status": validation_status,
        "observation_count": len(curve),
        "period_start": dates[0],
        "period_end": dates[-1],
        "metrics": computed,
        "benchmark_metrics": benchmark_metrics,
        "relative_metrics": relative,
        "turnover": {"cumulative_one_way": cumulative_turnover},
        "transaction_costs": transaction_costs,
        "readiness_summary": {
            "period_count": len(periods),
            "portfolio_ready_period_count": ready,
            "insufficient_coverage_period_count": insufficient,
            "ready_participation_rate": ready / len(periods),
        },
        "drawdown_series": drawdown_series,
        "lineage": {
            "historical_replay_manifest_sha256": _file_hash(replay_path),
            "historical_replay_payload_sha256": _canonical_hash(replay),
            "backtest_output_sha256": _file_hash(backtest_path),
            "backtest_payload_sha256": _canonical_hash(backtest),
            "backtest_configuration_sha256": backtest.get("configuration_sha256"),
            "backtest_data_manifest_sha256": backtest.get("data_manifest_sha256"),
        },
        "execution_boundary": dict(boundary),
    }
    result["certification_sha256"] = _canonical_hash(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Certify walk-forward performance analytics")
    parser.add_argument("--replay-manifest", required=True)
    parser.add_argument("--backtest-output", required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = certify_performance(
            replay_manifest_path=args.replay_manifest,
            backtest_output_path=args.backtest_output,
            authorization=args.authorization,
        )
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (PerformanceAnalyticsError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"status": result["status"], "observation_count": result["observation_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
