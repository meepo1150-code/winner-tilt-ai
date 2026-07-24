"""Deterministic research-only portfolio readiness certification."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ENGINE_VERSION = "1.0.0"


class PortfolioReadinessError(ValueError):
    """Raised when readiness certification fails closed."""


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PortfolioReadinessError("READINESS_JSON_OBJECT_REQUIRED")
    return value


def _require_boundary(value: Mapping[str, Any]) -> dict[str, bool]:
    boundary = value.get("execution_boundary")
    if not isinstance(boundary, Mapping):
        raise PortfolioReadinessError("READINESS_EXECUTION_BOUNDARY_REQUIRED")
    required = ("broker_connected", "orders_created", "orders_executed", "automatic_dca", "automatic_exits")
    if any(boundary.get(key) is not False for key in required):
        raise PortfolioReadinessError("READINESS_EXECUTION_BOUNDARY_FAILED")
    if value.get("broker_integration_enabled") not in (None, False):
        raise PortfolioReadinessError("READINESS_BROKER_FLAG_INVALID")
    return {key: False for key in required}


def _artifact_hash_matches(root: Path, manifest: Mapping[str, Any], name: str) -> Path:
    artifacts = manifest.get("artifacts")
    hashes = manifest.get("artifact_sha256")
    if not isinstance(artifacts, Mapping) or not isinstance(hashes, Mapping):
        raise PortfolioReadinessError("READINESS_MANIFEST_ARTIFACTS_REQUIRED")
    relative = artifacts.get(name)
    expected = hashes.get(name)
    if not isinstance(relative, str) or not isinstance(expected, str) or len(expected) != 64:
        raise PortfolioReadinessError("READINESS_ARTIFACT_REFERENCE_INVALID:" + name)
    path = root / relative
    if not path.is_file() or _file_hash(path) != expected:
        raise PortfolioReadinessError("READINESS_ARTIFACT_HASH_MISMATCH:" + name)
    return path


def certify_readiness(*, root: str | Path, run_manifest_path: str | Path,
                      portfolio_config_path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root_path = Path(root).resolve()
    manifest_path = Path(run_manifest_path)
    if not manifest_path.is_absolute():
        manifest_path = root_path / manifest_path
    config_path = Path(portfolio_config_path)
    if not config_path.is_absolute():
        config_path = root_path / config_path
    manifest = _read(manifest_path)
    config = _read(config_path)
    if manifest.get("status") != "COMPLETED_SHADOW_RESEARCH_ONLY":
        raise PortfolioReadinessError("READINESS_SHADOW_RUN_NOT_COMPLETED")
    boundary = _require_boundary(manifest)
    shadow_path = _artifact_hash_matches(root_path, manifest, "certified_shadow_portfolio")
    vintage_path = _artifact_hash_matches(root_path, manifest, "certified_score_vintage")
    journal_path = _artifact_hash_matches(root_path, manifest, "decision_journal_record")
    dashboard_path = _artifact_hash_matches(root_path, manifest, "dashboard_shadow_view")
    shadow = _read(shadow_path)
    _require_boundary(shadow)
    vintage = _read(vintage_path)
    journal = _read(journal_path)
    dashboard = _read(dashboard_path)
    portfolio = shadow.get("portfolio")
    if not isinstance(portfolio, Mapping):
        raise PortfolioReadinessError("READINESS_PORTFOLIO_REQUIRED")
    portfolio_cfg = config.get("portfolio")
    if not isinstance(portfolio_cfg, Mapping):
        raise PortfolioReadinessError("READINESS_PORTFOLIO_CONFIG_INVALID")
    holdings_target = int(portfolio_cfg.get("holdings_count", 0))
    reserves_target = int(portfolio_cfg.get("reserves_count", 0))
    required = holdings_target + reserves_target
    summary = portfolio.get("portfolio_summary") if isinstance(portfolio.get("portfolio_summary"), Mapping) else {}
    eligible = int(summary.get("eligible_candidate_count", len(portfolio.get("holdings", [])) + len(portfolio.get("reserves", []))))
    holdings = len(portfolio.get("holdings", [])) if isinstance(portfolio.get("holdings"), list) else 0
    reserves = len(portfolio.get("reserves", [])) if isinstance(portfolio.get("reserves"), list) else 0
    construction = portfolio.get("construction_status", "PORTFOLIO_CONSTRUCTED")
    if construction == "INSUFFICIENT_COVERAGE_RESEARCH_ONLY":
        status = "INSUFFICIENT_COVERAGE"
        reasons = ["Eligible certified coverage is below the frozen holdings plus reserves requirement."]
    elif holdings == holdings_target and reserves == reserves_target and eligible >= required:
        status = "PORTFOLIO_READY"
        reasons = ["Certified coverage and portfolio selections satisfy all frozen portfolio-count requirements."]
    else:
        raise PortfolioReadinessError("READINESS_PORTFOLIO_CONTRACT_INCONSISTENT")
    assessment = {
        "engine_version": ENGINE_VERSION,
        "status": status,
        "research_only": True,
        "run_id": manifest.get("run_id"),
        "as_of_date": manifest.get("as_of_date"),
        "coverage": {
            "holdings_target": holdings_target,
            "reserves_target": reserves_target,
            "required_candidate_count": required,
            "eligible_candidate_count": eligible,
            "selected_holdings_count": holdings,
            "selected_reserves_count": reserves,
            "candidate_shortfall": max(0, required - eligible),
        },
        "reasons": reasons,
        "execution_boundary": boundary,
        "source_hashes": {
            "run_manifest_sha256": _file_hash(manifest_path),
            "portfolio_config_sha256": _file_hash(config_path),
            "certified_shadow_portfolio_sha256": _file_hash(shadow_path),
            "certified_score_vintage_sha256": _file_hash(vintage_path),
            "decision_journal_sha256": _file_hash(journal_path),
            "dashboard_sha256": _file_hash(dashboard_path),
        },
    }
    assessment["assessment_sha256"] = _hash(assessment)
    package = {
        "schema_version": "1.0.0",
        "status": "CERTIFIED_INVESTMENT_COMMITTEE_RESEARCH_PACKAGE",
        "portfolio_readiness": status,
        "research_only": True,
        "executive_summary": reasons[0],
        "coverage": assessment["coverage"],
        "caveats": [
            "This package does not authorize trading or capital deployment.",
            "Portfolio readiness reflects only the certified inputs and frozen rules for this run.",
        ],
        "source_assessment_sha256": assessment["assessment_sha256"],
        "lineage": assessment["source_hashes"],
        "execution_boundary": boundary,
    }
    package["package_sha256"] = _hash(package)
    return assessment, package


def _write(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Certify research-only portfolio readiness")
    parser.add_argument("--root", default=".")
    parser.add_argument("--run-manifest", required=True)
    parser.add_argument("--portfolio-config", required=True)
    parser.add_argument("--assessment-output", required=True)
    parser.add_argument("--package-output", required=True)
    args = parser.parse_args()
    try:
        assessment, package = certify_readiness(root=args.root, run_manifest_path=args.run_manifest,
                                                portfolio_config_path=args.portfolio_config)
        _write(args.assessment_output, assessment)
        _write(args.package_output, package)
    except (PortfolioReadinessError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"status": assessment["status"], "assessment_sha256": assessment["assessment_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
