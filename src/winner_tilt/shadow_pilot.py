"""End-to-end orchestration for the certified non-executable shadow pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from winner_tilt.dashboard import build_shadow_portfolio_view_model
from winner_tilt.sec_to_score import run_pipeline
from winner_tilt.shadow_audit import build_shadow_journal_record
from winner_tilt.shadow_portfolio import run_shadow_portfolio

ENGINE_VERSION = "1.0.0"


class ShadowPilotError(ValueError):
    """Raised when the end-to-end shadow pilot fails closed."""


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _relative(path: str | Path, code: str) -> Path:
    value = Path(path)
    if value.is_absolute() or ".." in value.parts:
        raise ShadowPilotError(code)
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def run_shadow_pilot(
    *,
    root: str | Path,
    snapshot_path: str | Path,
    identifier_registry_path: str | Path,
    feature_definitions_path: str | Path,
    scoring_config_path: str | Path,
    portfolio_config_path: str | Path,
    universe_path: str | Path,
    output_dir: str | Path,
    information_cutoff: str,
    as_of_date: str,
    decision_timestamp_utc: str,
    run_id: str,
    sec_to_score_runner: Callable[..., dict[str, Any]] = run_pipeline,
    shadow_portfolio_runner: Callable[..., dict[str, Any]] = run_shadow_portfolio,
    audit_builder: Callable[..., dict[str, Any]] = build_shadow_journal_record,
) -> dict[str, Any]:
    """Run all certified stages against explicit immutable inputs only."""
    root_path = Path(root).resolve()
    inputs = {
        "snapshot": _relative(snapshot_path, "SHADOW_PILOT_SNAPSHOT_PATH_INVALID"),
        "identifier_registry": _relative(identifier_registry_path, "SHADOW_PILOT_IDENTIFIER_PATH_INVALID"),
        "feature_definitions": _relative(feature_definitions_path, "SHADOW_PILOT_FEATURE_PATH_INVALID"),
        "scoring_config": _relative(scoring_config_path, "SHADOW_PILOT_SCORING_PATH_INVALID"),
        "portfolio_config": _relative(portfolio_config_path, "SHADOW_PILOT_PORTFOLIO_PATH_INVALID"),
        "universe": _relative(universe_path, "SHADOW_PILOT_UNIVERSE_PATH_INVALID"),
    }
    output_rel = _relative(output_dir, "SHADOW_PILOT_OUTPUT_PATH_INVALID")
    if not run_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in run_id):
        raise ShadowPilotError("SHADOW_PILOT_RUN_ID_INVALID")
    for relative in inputs.values():
        if not (root_path / relative).is_file():
            raise ShadowPilotError(f"SHADOW_PILOT_INPUT_MISSING:{relative}")

    run_dir = root_path / output_rel / run_id
    if run_dir.exists():
        raise ShadowPilotError("SHADOW_PILOT_RUN_ALREADY_EXISTS")
    run_dir.mkdir(parents=True)

    vintage = sec_to_score_runner(
        snapshot_path=root_path / inputs["snapshot"],
        identifier_registry_path=root_path / inputs["identifier_registry"],
        feature_definitions_path=root_path / inputs["feature_definitions"],
        scoring_config_path=root_path / inputs["scoring_config"],
        universe_path=root_path / inputs["universe"],
        information_cutoff=information_cutoff,
    )
    vintage_rel = output_rel / run_id / "certified-score-vintage.json"
    _write_json(root_path / vintage_rel, vintage)

    shadow = shadow_portfolio_runner(
        vintage_path=root_path / vintage_rel,
        portfolio_config_path=root_path / inputs["portfolio_config"],
        universe_path=root_path / inputs["universe"],
        as_of_date=as_of_date,
    )
    boundary = shadow.get("execution_boundary")
    if not isinstance(boundary, dict) or any(value is not False for value in boundary.values()):
        raise ShadowPilotError("SHADOW_PILOT_EXECUTION_BOUNDARY_FAILED")
    shadow_rel = output_rel / run_id / "certified-shadow-portfolio.json"
    _write_json(root_path / shadow_rel, shadow)

    journal = audit_builder(
        shadow_path=shadow_rel,
        vintage_path=vintage_rel,
        universe_path=inputs["universe"],
        root=root_path,
        decision_timestamp_utc=decision_timestamp_utc,
        run_id=run_id,
    )
    journal_rel = output_rel / run_id / "decision-journal-record.json"
    _write_json(root_path / journal_rel, journal)

    dashboard = build_shadow_portfolio_view_model(shadow, journal)
    dashboard_rel = output_rel / run_id / "dashboard-shadow-view.json"
    _write_json(root_path / dashboard_rel, dashboard)

    artifacts = {
        "certified_score_vintage": str(vintage_rel),
        "certified_shadow_portfolio": str(shadow_rel),
        "decision_journal_record": str(journal_rel),
        "dashboard_shadow_view": str(dashboard_rel),
    }
    hashes = {name: hashlib.sha256((root_path / path).read_bytes()).hexdigest() for name, path in artifacts.items()}
    manifest = {
        "engine_version": ENGINE_VERSION,
        "run_id": run_id,
        "status": "COMPLETED_SHADOW_RESEARCH_ONLY",
        "information_cutoff": information_cutoff,
        "as_of_date": as_of_date,
        "decision_timestamp_utc": decision_timestamp_utc,
        "stages": {
            "sec_to_score": "CERTIFIED",
            "shadow_portfolio": "CERTIFIED",
            "decision_journal": "VALIDATED",
            "dashboard": "READ_ONLY",
        },
        "artifacts": artifacts,
        "artifact_sha256": hashes,
        "execution_boundary": dict(boundary),
        "live_sec_fetch_performed": False,
        "broker_integration_enabled": False,
    }
    manifest["manifest_sha256"] = _canonical_hash(manifest)
    manifest_rel = output_rel / run_id / "run-manifest.json"
    _write_json(root_path / manifest_rel, manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the end-to-end certified shadow pilot from an explicit SEC snapshot")
    parser.add_argument("--root", default=".")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--identifier-registry", required=True)
    parser.add_argument("--feature-definitions", required=True)
    parser.add_argument("--scoring-config", required=True)
    parser.add_argument("--portfolio-config", required=True)
    parser.add_argument("--universe", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--information-cutoff", required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--decision-timestamp", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    result = run_shadow_pilot(
        root=args.root, snapshot_path=args.snapshot, identifier_registry_path=args.identifier_registry,
        feature_definitions_path=args.feature_definitions, scoring_config_path=args.scoring_config,
        portfolio_config_path=args.portfolio_config, universe_path=args.universe,
        output_dir=args.output_dir, information_cutoff=args.information_cutoff,
        as_of_date=args.as_of_date, decision_timestamp_utc=args.decision_timestamp, run_id=args.run_id,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
