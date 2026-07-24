"""Deterministic factor attribution and explainability certification."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

ENGINE_VERSION = "1.0.0"
AUTHORIZATION_PHRASE = "AUTHORIZE_FACTOR_ATTRIBUTION_RESEARCH_ONLY"
TOLERANCE = 1e-9


class FactorAttributionError(ValueError):
    """Raised when attribution certification fails closed."""


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite(value: Any, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FactorAttributionError(code)
    result = float(value)
    if not math.isfinite(result):
        raise FactorAttributionError(code)
    return result


def discover_inputs(path: str | Path) -> list[Path]:
    root = Path(path)
    files = [root] if root.is_file() else sorted(root.rglob("*.json"))
    files = [item for item in files if item.is_file()]
    if not files:
        raise FactorAttributionError("FACTOR_ATTRIBUTION_INPUT_REQUIRED")
    return files


def _execution_boundary(payload: Mapping[str, Any]) -> None:
    boundary = payload.get("execution_boundary", {})
    if not isinstance(boundary, Mapping):
        raise FactorAttributionError("FACTOR_ATTRIBUTION_EXECUTION_BOUNDARY_INVALID")
    protected = ("broker_connected", "orders_created", "orders_executed", "automatic_dca", "automatic_exits")
    if any(boundary.get(key) is not False for key in protected):
        raise FactorAttributionError("FACTOR_ATTRIBUTION_EXECUTION_BOUNDARY_VIOLATION")


def certify_attribution(*, score_input_path: str | Path, replay_manifest_path: str | Path,
                        performance_certification_path: str | Path, authorization: str) -> dict[str, Any]:
    if authorization != AUTHORIZATION_PHRASE:
        raise FactorAttributionError("FACTOR_ATTRIBUTION_AUTHORIZATION_REQUIRED")

    score_files = discover_inputs(score_input_path)
    replay_path = Path(replay_manifest_path)
    performance_path = Path(performance_certification_path)
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    performance = json.loads(performance_path.read_text(encoding="utf-8"))

    if replay.get("status") != "CERTIFIED_HISTORICAL_REPLAY_RESEARCH_ONLY":
        raise FactorAttributionError("FACTOR_ATTRIBUTION_REPLAY_NOT_CERTIFIED")
    if performance.get("status") != "PERFORMANCE_CERTIFIED":
        raise FactorAttributionError("FACTOR_ATTRIBUTION_PERFORMANCE_NOT_CERTIFIED")
    _execution_boundary(replay)
    _execution_boundary(performance)

    periods = replay.get("periods")
    if not isinstance(periods, list) or not periods:
        raise FactorAttributionError("FACTOR_ATTRIBUTION_REPLAY_PERIODS_REQUIRED")
    cutoffs = [item.get("information_cutoff") for item in periods if isinstance(item, Mapping)]
    if len(cutoffs) != len(periods) or any(not isinstance(item, str) for item in cutoffs):
        raise FactorAttributionError("FACTOR_ATTRIBUTION_REPLAY_PERIOD_INVALID")
    if cutoffs != sorted(cutoffs) or len(set(cutoffs)) != len(cutoffs):
        raise FactorAttributionError("FACTOR_ATTRIBUTION_REPLAY_ORDER_INVALID")

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    ordered_hashes: list[str] = []
    for path in score_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        candidates = payload.get("results", payload.get("securities"))
        cutoff = payload.get("information_cutoff")
        if not isinstance(cutoff, str) or cutoff not in cutoffs:
            raise FactorAttributionError("FACTOR_ATTRIBUTION_CUTOFF_NOT_IN_REPLAY")
        if not isinstance(candidates, list) or not candidates:
            raise FactorAttributionError("FACTOR_ATTRIBUTION_RESULTS_REQUIRED")
        ordered_hashes.append(_file_hash(path))
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                raise FactorAttributionError("FACTOR_ATTRIBUTION_RESULT_INVALID")
            security_id = candidate.get("security_id")
            if not isinstance(security_id, str) or not security_id:
                raise FactorAttributionError("FACTOR_ATTRIBUTION_SECURITY_ID_INVALID")
            key = (cutoff, security_id)
            if key in seen:
                raise FactorAttributionError("FACTOR_ATTRIBUTION_DUPLICATE_SECURITY_PERIOD")
            seen.add(key)
            factors = candidate.get("factor_contributions")
            if not isinstance(factors, Mapping) or not factors:
                raise FactorAttributionError("FACTOR_ATTRIBUTION_FACTORS_REQUIRED")
            normalized: dict[str, float] = {}
            for name, value in factors.items():
                if not isinstance(name, str) or not name.strip():
                    raise FactorAttributionError("FACTOR_ATTRIBUTION_FACTOR_NAME_INVALID")
                normalized[name] = _finite(value, "FACTOR_ATTRIBUTION_FACTOR_VALUE_INVALID")
            total_score = _finite(candidate.get("total_score"), "FACTOR_ATTRIBUTION_TOTAL_SCORE_INVALID")
            base_score = _finite(candidate.get("base_score", 0.0), "FACTOR_ATTRIBUTION_BASE_SCORE_INVALID")
            recomputed = base_score + sum(normalized.values())
            if abs(recomputed - total_score) > TOLERANCE:
                raise FactorAttributionError("FACTOR_ATTRIBUTION_SCORE_MISMATCH")
            rows.append({
                "information_cutoff": cutoff,
                "security_id": security_id,
                "sector": str(candidate.get("sector", "UNKNOWN")),
                "eligible": candidate.get("eligible") is True,
                "base_score": base_score,
                "total_score": total_score,
                "factor_contributions": dict(sorted(normalized.items())),
                "positive_drivers": sorted(
                    ({"factor": name, "contribution": value} for name, value in normalized.items() if value > 0),
                    key=lambda item: (-item["contribution"], item["factor"]),
                ),
                "negative_drivers": sorted(
                    ({"factor": name, "contribution": value} for name, value in normalized.items() if value < 0),
                    key=lambda item: (item["contribution"], item["factor"]),
                ),
                "eligibility_reason": "ELIGIBLE_SCORE_RECORD" if candidate.get("eligible") is True else "RESEARCH_ONLY_NOT_ELIGIBLE",
            })

    rows.sort(key=lambda item: (item["information_cutoff"], item["security_id"]))
    factor_totals: defaultdict[str, float] = defaultdict(float)
    sector_totals: defaultdict[str, float] = defaultdict(float)
    security_totals: defaultdict[str, float] = defaultdict(float)
    historical: dict[str, dict[str, float]] = {}
    for row in rows:
        bucket = historical.setdefault(row["information_cutoff"], defaultdict(float))
        for factor, value in row["factor_contributions"].items():
            factor_totals[factor] += value
            bucket[factor] += value
            sector_totals[row["sector"]] += value
            security_totals[row["security_id"]] += value

    insufficient = int(replay.get("insufficient_coverage_period_count", 0))
    result = {
        "engine_version": ENGINE_VERSION,
        "status": "FACTOR_ATTRIBUTION_CERTIFIED_RESEARCH_ONLY",
        "certification_scope": "RESEARCH_ONLY_WITH_INSUFFICIENT_COVERAGE" if insufficient else "RESEARCH_ONLY",
        "record_count": len(rows),
        "period_count": len({row["information_cutoff"] for row in rows}),
        "security_count": len({row["security_id"] for row in rows}),
        "factor_count": len(factor_totals),
        "security_explanations": rows,
        "aggregate_attribution": {
            "by_factor": dict(sorted(factor_totals.items())),
            "by_security": dict(sorted(security_totals.items())),
            "by_sector": dict(sorted(sector_totals.items())),
            "by_period": {cutoff: dict(sorted(values.items())) for cutoff, values in sorted(historical.items())},
        },
        "readiness_summary": {
            "portfolio_ready_period_count": int(replay.get("portfolio_ready_period_count", 0)),
            "insufficient_coverage_period_count": insufficient,
            "insufficient_coverage_preserved_as_research_only": True,
        },
        "lineage": {
            "historical_replay_sha256": _file_hash(replay_path),
            "performance_certification_sha256": _file_hash(performance_path),
            "ordered_score_inputs_sha256": _canonical_hash(ordered_hashes),
        },
        "execution_boundary": {
            "broker_connected": False,
            "orders_created": False,
            "orders_executed": False,
            "automatic_dca": False,
            "automatic_exits": False,
        },
    }
    result["certification_sha256"] = _canonical_hash(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Certify deterministic factor attribution and explainability")
    parser.add_argument("--score-input", required=True)
    parser.add_argument("--replay-manifest", required=True)
    parser.add_argument("--performance-certification", required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = certify_attribution(score_input_path=args.score_input, replay_manifest_path=args.replay_manifest,
                                     performance_certification_path=args.performance_certification,
                                     authorization=args.authorization)
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (FactorAttributionError, OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"status": result["status"], "record_count": result["record_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
