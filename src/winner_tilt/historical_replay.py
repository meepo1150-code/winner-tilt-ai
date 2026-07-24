"""Deterministic historical replay and walk-forward certification."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ENGINE_VERSION = "1.0.0"
AUTHORIZATION_PHRASE = "AUTHORIZE_HISTORICAL_REPLAY_RESEARCH_ONLY"


class HistoricalReplayError(ValueError):
    """Raised when historical replay certification fails closed."""


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalReplayError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HistoricalReplayError(code) from exc
    if parsed.tzinfo is None:
        raise HistoricalReplayError(code)
    return parsed.astimezone(timezone.utc)


def discover_vintages(path: str | Path) -> list[Path]:
    root = Path(path)
    files = [root] if root.is_file() else sorted(root.rglob("*.json"))
    files = [item for item in files if item.is_file()]
    if not files:
        raise HistoricalReplayError("HISTORICAL_REPLAY_VINTAGES_REQUIRED")
    return files


def _extract_vintage(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    vintages = payload.get("vintages")
    if isinstance(vintages, list) and len(vintages) == 1 and isinstance(vintages[0], Mapping):
        return vintages[0]
    if payload.get("information_cutoff") and isinstance(payload.get("results"), list):
        return payload
    raise HistoricalReplayError("HISTORICAL_REPLAY_SINGLE_VINTAGE_REQUIRED")


def certify_replay(*, vintage_path: str | Path, portfolio_config_path: str | Path,
                   authorization: str) -> dict[str, Any]:
    if authorization != AUTHORIZATION_PHRASE:
        raise HistoricalReplayError("HISTORICAL_REPLAY_AUTHORIZATION_REQUIRED")
    config_path = Path(portfolio_config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    portfolio_cfg = config.get("portfolio")
    if not isinstance(portfolio_cfg, Mapping):
        raise HistoricalReplayError("HISTORICAL_REPLAY_PORTFOLIO_CONFIG_INVALID")
    holdings_target = int(portfolio_cfg.get("holdings_count", 0))
    reserves_target = int(portfolio_cfg.get("reserves_count", 0))
    if holdings_target < 1 or reserves_target < 0:
        raise HistoricalReplayError("HISTORICAL_REPLAY_TARGET_INVALID")
    required = holdings_target + reserves_target

    periods: list[dict[str, Any]] = []
    seen_cutoffs: set[str] = set()
    for path in discover_vintages(vintage_path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        vintage = _extract_vintage(payload)
        certification = vintage.get("certification")
        if not isinstance(certification, Mapping) or certification.get("status") != "CERTIFIED":
            raise HistoricalReplayError("HISTORICAL_REPLAY_UNCERTIFIED_VINTAGE")
        cutoff_raw = vintage.get("information_cutoff")
        cutoff = _utc(cutoff_raw, "HISTORICAL_REPLAY_CUTOFF_INVALID")
        cutoff_key = cutoff.isoformat().replace("+00:00", "Z")
        if cutoff_key in seen_cutoffs:
            raise HistoricalReplayError("HISTORICAL_REPLAY_DUPLICATE_CUTOFF")
        seen_cutoffs.add(cutoff_key)
        generated = _utc(vintage.get("generated_at", cutoff_key), "HISTORICAL_REPLAY_GENERATED_AT_INVALID")
        if generated < cutoff:
            raise HistoricalReplayError("HISTORICAL_REPLAY_GENERATED_BEFORE_CUTOFF")
        results = vintage.get("results")
        if not isinstance(results, list) or not results:
            raise HistoricalReplayError("HISTORICAL_REPLAY_RESULTS_REQUIRED")
        eligible = 0
        securities: set[str] = set()
        for row in results:
            if not isinstance(row, Mapping):
                raise HistoricalReplayError("HISTORICAL_REPLAY_RESULT_INVALID")
            sid = row.get("security_id")
            if not isinstance(sid, str) or not sid or sid in securities:
                raise HistoricalReplayError("HISTORICAL_REPLAY_SECURITY_ID_INVALID")
            securities.add(sid)
            available = _utc(row.get("available_at", cutoff_key), "HISTORICAL_REPLAY_AVAILABLE_AT_INVALID")
            if available > cutoff:
                raise HistoricalReplayError("HISTORICAL_REPLAY_LOOKAHEAD")
            if row.get("eligible") is True and row.get("total_score") is not None:
                eligible += 1
        status = "PORTFOLIO_READY" if eligible >= required else "INSUFFICIENT_COVERAGE"
        periods.append({
            "information_cutoff": cutoff_key,
            "status": status,
            "eligible_candidate_count": eligible,
            "required_candidate_count": required,
            "candidate_shortfall": max(0, required - eligible),
            "result_count": len(results),
            "source_path": str(path),
            "source_file_sha256": _file_hash(path),
            "vintage_payload_sha256": _canonical_hash(vintage),
        })

    periods.sort(key=lambda item: item["information_cutoff"])
    if any(periods[i]["information_cutoff"] >= periods[i + 1]["information_cutoff"] for i in range(len(periods) - 1)):
        raise HistoricalReplayError("HISTORICAL_REPLAY_ORDER_INVALID")
    ready = sum(item["status"] == "PORTFOLIO_READY" for item in periods)
    insufficient = len(periods) - ready
    result = {
        "engine_version": ENGINE_VERSION,
        "status": "CERTIFIED_HISTORICAL_REPLAY_RESEARCH_ONLY",
        "period_count": len(periods),
        "portfolio_ready_period_count": ready,
        "insufficient_coverage_period_count": insufficient,
        "holdings_target": holdings_target,
        "reserves_target": reserves_target,
        "required_candidate_count": required,
        "periods": periods,
        "lineage": {
            "portfolio_config_sha256": _file_hash(config_path),
            "ordered_source_sha256": _canonical_hash([item["source_file_sha256"] for item in periods]),
        },
        "execution_boundary": {
            "broker_connected": False,
            "orders_created": False,
            "orders_executed": False,
            "automatic_dca": False,
            "automatic_exits": False,
        },
    }
    result["manifest_sha256"] = _canonical_hash(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Certify deterministic historical score-vintage replay")
    parser.add_argument("--vintages", required=True)
    parser.add_argument("--portfolio-config", required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = certify_replay(vintage_path=args.vintages, portfolio_config_path=args.portfolio_config,
                                authorization=args.authorization)
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (HistoricalReplayError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"status": result["status"], "period_count": result["period_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
