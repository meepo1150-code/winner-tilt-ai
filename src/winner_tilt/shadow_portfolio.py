"""Certified score-vintage to non-executable shadow portfolio bridge."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ENGINE_VERSION = "1.0.0"


class ShadowPortfolioError(ValueError):
    """Raised when shadow portfolio certification fails closed."""


def _hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _parse_utc(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ShadowPortfolioError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ShadowPortfolioError(code) from exc
    if parsed.tzinfo is None:
        raise ShadowPortfolioError(code)
    return parsed.astimezone(timezone.utc)


def certify_vintage(payload: Mapping[str, Any], *, as_of_date: str) -> dict[str, Any]:
    vintages = payload.get("vintages")
    if not isinstance(vintages, list) or len(vintages) != 1:
        raise ShadowPortfolioError("SHADOW_PORTFOLIO_SINGLE_VINTAGE_REQUIRED")
    vintage = vintages[0]
    certification = vintage.get("certification")
    if not isinstance(certification, Mapping) or certification.get("status") != "CERTIFIED":
        raise ShadowPortfolioError("SHADOW_PORTFOLIO_UNCERTIFIED_VINTAGE")
    cutoff = _parse_utc(vintage.get("information_cutoff"), "SHADOW_PORTFOLIO_INVALID_CUTOFF")
    as_of = _parse_utc(f"{as_of_date}T23:59:59Z", "SHADOW_PORTFOLIO_INVALID_AS_OF_DATE")
    if cutoff > as_of:
        raise ShadowPortfolioError("SHADOW_PORTFOLIO_FUTURE_CUTOFF")
    lineage = vintage.get("lineage")
    if not isinstance(lineage, list) or not lineage:
        raise ShadowPortfolioError("SHADOW_PORTFOLIO_LINEAGE_REQUIRED")
    results = vintage.get("results")
    if not isinstance(results, list) or not results:
        raise ShadowPortfolioError("SHADOW_PORTFOLIO_RESULTS_REQUIRED")
    seen: set[str] = set()
    ranks: list[int] = []
    for row in results:
        sid = row.get("security_id")
        if not isinstance(sid, str) or not sid or sid in seen:
            raise ShadowPortfolioError("SHADOW_PORTFOLIO_INVALID_SECURITY_ID")
        seen.add(sid)
        available = _parse_utc(row.get("available_at"), "SHADOW_PORTFOLIO_AVAILABLE_AT_REQUIRED")
        if available > cutoff:
            raise ShadowPortfolioError("SHADOW_PORTFOLIO_LOOKAHEAD")
        if row.get("eligible") and row.get("total_score") is not None:
            rank = row.get("overall_rank")
            if not isinstance(rank, int) or rank < 1:
                raise ShadowPortfolioError("SHADOW_PORTFOLIO_INVALID_RANK")
            ranks.append(rank)
    if len(ranks) != len(set(ranks)):
        raise ShadowPortfolioError("SHADOW_PORTFOLIO_DUPLICATE_RANK")
    return {"status": "CERTIFIED", "cutoff": vintage["information_cutoff"], "result_count": len(results), "vintage_sha256": _hash(vintage)}


def _validate_output(output: Mapping[str, Any], cfg: Mapping[str, Any]) -> None:
    holdings = output.get("holdings")
    reserves = output.get("reserves")
    if not isinstance(holdings, list) or len(holdings) != cfg["portfolio"]["holdings_count"]:
        raise ShadowPortfolioError("SHADOW_PORTFOLIO_HOLDINGS_CONTRACT_FAILED")
    if not isinstance(reserves, list) or len(reserves) != cfg["portfolio"]["reserves_count"]:
        raise ShadowPortfolioError("SHADOW_PORTFOLIO_RESERVES_CONTRACT_FAILED")
    ids = [row.get("security_id") for row in holdings + reserves]
    if any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
        raise ShadowPortfolioError("SHADOW_PORTFOLIO_DUPLICATE_SELECTION")
    weights = [row.get("weight") for row in holdings]
    if any(not isinstance(x, (int, float)) or x < 0 for x in weights) or abs(sum(weights) - 1.0) > 1e-8:
        raise ShadowPortfolioError("SHADOW_PORTFOLIO_WEIGHT_CONTRACT_FAILED")


def run_shadow_portfolio(*, vintage_path: str | Path, portfolio_config_path: str | Path,
                         universe_path: str | Path, as_of_date: str,
                         previous_path: str | Path | None = None) -> dict[str, Any]:
    vintage_payload = json.loads(Path(vintage_path).read_text(encoding="utf-8"))
    config = json.loads(Path(portfolio_config_path).read_text(encoding="utf-8"))
    certification = certify_vintage(vintage_payload, as_of_date=as_of_date)
    vintage = vintage_payload["vintages"][0]
    scoring_run = {"configuration_sha256": vintage.get("scoring_configuration_sha256"), "results": vintage["results"]}
    with tempfile.TemporaryDirectory(prefix="winner-tilt-shadow-") as tmp:
        score_path = Path(tmp) / "scores.json"
        output_path = Path(tmp) / "portfolio.json"
        score_path.write_text(json.dumps(scoring_run), encoding="utf-8")
        command = [sys.executable, "-m", "winner_tilt.portfolio", "--config", str(portfolio_config_path),
                   "--universe", str(universe_path), "--scores", str(score_path), "--output", str(output_path),
                   "--as-of-date", as_of_date]
        if previous_path:
            command.extend(["--previous", str(previous_path)])
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise ShadowPortfolioError("SHADOW_PORTFOLIO_ENGINE_FAILED:" + completed.stderr.strip())
        portfolio = json.loads(output_path.read_text(encoding="utf-8"))
    _validate_output(portfolio, config)
    result = {
        "engine_version": ENGINE_VERSION,
        "mode": "SHADOW_RESEARCH_ONLY",
        "as_of_date": as_of_date,
        "certification": certification,
        "portfolio": portfolio,
        "lineage": {
            "certified_vintage_sha256": _hash(vintage_payload),
            "portfolio_config_sha256": _hash(config),
            "universe_sha256": hashlib.sha256(Path(universe_path).read_bytes()).hexdigest(),
            "portfolio_output_sha256": _hash(portfolio),
        },
        "execution_boundary": {"broker_connected": False, "orders_created": False, "orders_executed": False,
                               "automatic_dca": False, "automatic_exits": False},
    }
    result["output_sha256"] = _hash(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a certified non-executable shadow portfolio")
    parser.add_argument("--vintage", required=True)
    parser.add_argument("--portfolio-config", required=True)
    parser.add_argument("--universe", required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--previous")
    args = parser.parse_args()
    result = run_shadow_portfolio(vintage_path=args.vintage, portfolio_config_path=args.portfolio_config,
                                  universe_path=args.universe, as_of_date=args.as_of_date,
                                  previous_path=args.previous)
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
