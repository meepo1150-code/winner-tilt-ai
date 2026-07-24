from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, pstdev

AUTHORIZATION = "AUTHORIZE_PORTFOLIO_RISK_RESEARCH_ONLY"
BOUNDARY = {
    "broker_connected": False,
    "orders_created": False,
    "orders_executed": False,
    "automatic_dca": False,
    "automatic_exits": False,
}


def _load(path: Path) -> dict:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"Non-finite {name}")
    return value


def _returns(values: list[float]) -> list[float]:
    if len(values) < 2:
        raise ValueError("At least two observations are required")
    if any(v <= 0 for v in values):
        raise ValueError("Portfolio and benchmark values must be positive")
    return [values[i] / values[i - 1] - 1.0 for i in range(1, len(values))]


def _covariance(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("Aligned non-empty return series required")
    ma, mb = mean(a), mean(b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / len(a)


def certify(
    portfolio_path: Path,
    performance_path: Path,
    replay_path: Path,
    authorization: str,
) -> dict:
    if authorization != AUTHORIZATION:
        raise ValueError("Explicit research-only authorization required")
    portfolio = _load(portfolio_path)
    performance = _load(performance_path)
    replay = _load(replay_path)
    if performance.get("status") != "PERFORMANCE_CERTIFIED":
        raise ValueError("Performance input is not certified")
    if replay.get("status") != "CERTIFIED_HISTORICAL_REPLAY_RESEARCH_ONLY":
        raise ValueError("Replay input is not certified")
    if any(bool(v) for v in performance.get("execution_boundary", {}).values()):
        raise ValueError("Upstream execution boundary violation")

    positions = portfolio.get("positions")
    if not isinstance(positions, list) or not positions:
        raise ValueError("Portfolio positions are required")
    seen: set[str] = set()
    normalized = []
    for row in positions:
        symbol = str(row["symbol"])
        if symbol in seen:
            raise ValueError(f"Duplicate position: {symbol}")
        seen.add(symbol)
        weight = _finite(row["weight"], f"weight:{symbol}")
        if weight < 0:
            raise ValueError("Negative weights are not supported")
        normalized.append({"symbol": symbol, "sector": str(row.get("sector", "Unknown")), "weight": weight})
    weight_sum = sum(p["weight"] for p in normalized)
    if abs(weight_sum - 1.0) > 1e-9:
        raise ValueError(f"Weights must sum to 1.0, got {weight_sum}")

    weights = [p["weight"] for p in normalized]
    hhi = sum(w * w for w in weights)
    effective_positions = 1.0 / hhi
    max_weight = max(weights)
    top3 = sum(sorted(weights, reverse=True)[:3])
    diversification_score = max(0.0, min(100.0, 100.0 * (1.0 - hhi)))
    sectors: dict[str, float] = {}
    for p in normalized:
        sectors[p["sector"]] = sectors.get(p["sector"], 0.0) + p["weight"]
    sector_hhi = sum(v * v for v in sectors.values())

    curve = performance.get("equity_curve")
    if not isinstance(curve, list) or len(curve) < 2:
        raise ValueError("Certified performance equity curve is required")
    dates = [str(r["date"]) for r in curve]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ValueError("Equity curve dates must be unique and ordered")
    pv = [_finite(r["portfolio_value"], "portfolio_value") for r in curve]
    bv = [_finite(r["benchmark_value"], "benchmark_value") for r in curve]
    pr = _returns(pv)
    br = _returns(bv)
    active = [x - y for x, y in zip(pr, br)]
    volatility = pstdev(pr) if len(pr) > 1 else 0.0
    downside = [min(x, 0.0) for x in pr]
    downside_volatility = math.sqrt(mean([x * x for x in downside]))
    benchmark_variance = pstdev(br) ** 2 if len(br) > 1 else 0.0
    beta = _covariance(pr, br) / benchmark_variance if benchmark_variance > 0 else 0.0
    tracking_error = pstdev(active) if len(active) > 1 else 0.0
    information_ratio = mean(active) / tracking_error if tracking_error > 0 else 0.0

    ranked = sorted(normalized, key=lambda x: (-x["weight"], x["symbol"]))
    risk_contributors = [
        {"symbol": p["symbol"], "sector": p["sector"], "weight": p["weight"], "concentration_contribution": p["weight"] ** 2}
        for p in ranked
    ]
    readiness = {
        "period_count": int(replay.get("period_count", 0)),
        "portfolio_ready_period_count": int(replay.get("portfolio_ready_period_count", 0)),
        "insufficient_coverage_period_count": int(replay.get("insufficient_coverage_period_count", 0)),
        "insufficient_coverage_preserved": int(replay.get("insufficient_coverage_period_count", 0)) > 0,
    }
    return {
        "status": "PORTFOLIO_RISK_CERTIFIED_RESEARCH_ONLY",
        "research_only": True,
        "position_count": len(normalized),
        "sector_count": len(sectors),
        "concentration": {
            "hhi": hhi,
            "effective_number_of_positions": effective_positions,
            "maximum_position_weight": max_weight,
            "top_3_weight": top3,
            "sector_hhi": sector_hhi,
            "diversification_score": diversification_score,
        },
        "market_risk": {
            "volatility": volatility,
            "downside_volatility": downside_volatility,
            "beta": beta,
            "tracking_error": tracking_error,
            "information_ratio": information_ratio,
            "observation_count": len(curve),
        },
        "sector_exposure": dict(sorted(sectors.items())),
        "largest_holdings": ranked[:5],
        "risk_contributors": risk_contributors,
        "readiness_summary": readiness,
        "lineage": {
            "portfolio_sha256": _sha(portfolio_path),
            "performance_sha256": _sha(performance_path),
            "historical_replay_sha256": _sha(replay_path),
        },
        "execution_boundary": dict(BOUNDARY),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Certify deterministic portfolio risk analytics")
    parser.add_argument("--portfolio", required=True, type=Path)
    parser.add_argument("--performance", required=True, type=Path)
    parser.add_argument("--replay-manifest", required=True, type=Path)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = certify(args.portfolio, args.performance, args.replay_manifest, args.authorization)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
