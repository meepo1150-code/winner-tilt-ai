"""Certified SEC EDGAR snapshot to Winner Tilt score-vintage pipeline.

The pipeline is additive and fail-closed. It re-certifies an immutable M11
snapshot, resolves CIKs through a versioned identifier registry, builds M12
point-in-time observations, invokes the frozen scoring CLI, and emits a
backtest-compatible score vintage with immutable lineage hashes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from winner_tilt.fundamental_features import (
    build_fundamental_observations,
    write_scoring_observations,
)

PIPELINE_VERSION = "1.0.0"
SEC_PROVIDER_ID = "sec-edgar-companyfacts"


class SecToScoreError(ValueError):
    """Raised when any certification or downstream contract gate fails."""


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_utc(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SecToScoreError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SecToScoreError(code) from exc
    if parsed.tzinfo is None:
        raise SecToScoreError(code)
    return parsed.astimezone(timezone.utc)


def certify_snapshot(snapshot: Mapping[str, Any], information_cutoff: str) -> dict[str, Any]:
    cutoff = parse_utc(information_cutoff, "SEC_TO_SCORE_INVALID_CUTOFF")
    if snapshot.get("dataset_type") != "fundamentals":
        raise SecToScoreError("SEC_TO_SCORE_DATASET_TYPE_INVALID")
    if snapshot.get("provider_id") != SEC_PROVIDER_ID:
        raise SecToScoreError("SEC_TO_SCORE_PROVIDER_INVALID")
    if snapshot.get("pilot_tag") != "ingest_only_no_downstream_consumption":
        raise SecToScoreError("SEC_TO_SCORE_PILOT_TAG_REQUIRED")
    provenance = snapshot.get("provenance")
    if not isinstance(provenance, Mapping):
        raise SecToScoreError("SEC_TO_SCORE_PROVENANCE_REQUIRED")
    if provenance.get("raw_payload_retained") is not False:
        raise SecToScoreError("SEC_TO_SCORE_RAW_RETENTION_POLICY_INVALID")
    if not provenance.get("raw_content_sha256"):
        raise SecToScoreError("SEC_TO_SCORE_SOURCE_HASH_REQUIRED")
    rows = snapshot.get("rows")
    if not isinstance(rows, list) or not rows:
        raise SecToScoreError("SEC_TO_SCORE_ROWS_REQUIRED")
    ids: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise SecToScoreError("SEC_TO_SCORE_ROW_INVALID")
        required = ("id", "cik", "concept", "unit", "value", "report_end", "accepted_timestamp", "accession_number")
        if any(row.get(field) in (None, "") for field in required):
            raise SecToScoreError("SEC_TO_SCORE_ROW_METADATA_MISSING")
        row_id = str(row["id"])
        if row_id in ids:
            raise SecToScoreError("SEC_TO_SCORE_DUPLICATE_ROW_ID")
        ids.add(row_id)
        available = parse_utc(row["accepted_timestamp"], "SEC_TO_SCORE_INVALID_AVAILABLE_AT")
        if available > cutoff:
            raise SecToScoreError("SEC_TO_SCORE_FUTURE_FACT")
    acquisition = parse_utc(snapshot.get("acquisition_timestamp"), "SEC_TO_SCORE_ACQUISITION_REQUIRED")
    if acquisition < max(parse_utc(r["accepted_timestamp"], "SEC_TO_SCORE_INVALID_AVAILABLE_AT") for r in rows):
        raise SecToScoreError("SEC_TO_SCORE_ACQUISITION_PRECEDES_PUBLICATION")
    return {
        "status": "CERTIFIED",
        "provider_id": SEC_PROVIDER_ID,
        "row_count": len(rows),
        "snapshot_payload_sha256": canonical_hash(snapshot),
        "raw_content_sha256": provenance["raw_content_sha256"],
        "information_cutoff": cutoff.isoformat().replace("+00:00", "Z"),
    }


def load_identifier_registry(path: str | Path) -> tuple[dict[str, str], str]:
    mapping: dict[str, str] = {}
    reverse: dict[str, str] = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SecToScoreError("SEC_TO_SCORE_IDENTIFIER_REGISTRY_EMPTY")
    for row in rows:
        cik = str(row.get("cik", "")).strip().zfill(10)
        sid = str(row.get("security_id", "")).strip()
        if not cik.isdigit() or len(cik) != 10 or not sid:
            raise SecToScoreError("SEC_TO_SCORE_IDENTIFIER_INVALID")
        if row.get("status") != "ACTIVE":
            continue
        if cik in mapping or sid in reverse:
            raise SecToScoreError("SEC_TO_SCORE_IDENTIFIER_NOT_ONE_TO_ONE")
        mapping[cik] = sid
        reverse[sid] = cik
    if not mapping:
        raise SecToScoreError("SEC_TO_SCORE_NO_ACTIVE_IDENTIFIERS")
    return mapping, file_sha256(path)


def map_snapshot_rows(rows: list[Mapping[str, Any]], identifiers: Mapping[str, str]) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for source in rows:
        cik = str(source.get("cik", "")).zfill(10)
        security_id = identifiers.get(cik)
        if security_id is None:
            raise SecToScoreError(f"SEC_TO_SCORE_UNMAPPED_CIK:{cik}")
        row = dict(source)
        row["source_security_id"] = row.get("security_id")
        row["security_id"] = security_id
        mapped.append(row)
    return sorted(mapped, key=lambda row: str(row["id"]))


def validate_score_output(score: Mapping[str, Any], cutoff: str, feature_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    results = score.get("results")
    if not isinstance(results, list) or not results:
        raise SecToScoreError("SEC_TO_SCORE_SCORING_RESULTS_REQUIRED")
    observations = feature_payload.get("observations", [])
    available_by_security: dict[str, list[str]] = {}
    for row in observations:
        if row.get("available_at"):
            available_by_security.setdefault(row["security_id"], []).append(row["available_at"])
    cutoff_dt = parse_utc(cutoff, "SEC_TO_SCORE_INVALID_CUTOFF")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in results:
        sid = result.get("security_id")
        if not isinstance(sid, str) or not sid or sid in seen:
            raise SecToScoreError("SEC_TO_SCORE_SCORE_ID_INVALID")
        seen.add(sid)
        available_values = available_by_security.get(sid, [])
        available_at = max(available_values) if available_values else cutoff
        if parse_utc(available_at, "SEC_TO_SCORE_INVALID_SCORE_AVAILABLE_AT") > cutoff_dt:
            raise SecToScoreError("SEC_TO_SCORE_SCORE_LOOKAHEAD")
        enriched = dict(result)
        enriched["available_at"] = available_at
        enriched["fundamental_feature_output_sha256"] = feature_payload.get("output_sha256")
        output.append(enriched)
    return output


def run_pipeline(
    *,
    snapshot_path: str | Path,
    identifier_registry_path: str | Path,
    feature_definitions_path: str | Path,
    scoring_config_path: str | Path,
    universe_path: str | Path,
    information_cutoff: str,
    python_executable: str | None = None,
) -> dict[str, Any]:
    snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    certification = certify_snapshot(snapshot, information_cutoff)
    identifiers, registry_hash = load_identifier_registry(identifier_registry_path)
    mapped_rows = map_snapshot_rows(snapshot["rows"], identifiers)
    definitions_payload = json.loads(Path(feature_definitions_path).read_text(encoding="utf-8"))
    definitions = definitions_payload.get("features", definitions_payload)
    features = build_fundamental_observations(
        mapped_rows,
        definitions,
        information_cutoff=information_cutoff,
    )
    with tempfile.TemporaryDirectory(prefix="winner-tilt-m13-") as temp_dir:
        temp = Path(temp_dir)
        observations_path = temp / "observations.csv"
        scoring_output_path = temp / "scores.json"
        write_scoring_observations(features, observations_path)
        command = [
            python_executable or sys.executable,
            "-m",
            "winner_tilt.scoring",
            "--config", str(scoring_config_path),
            "--universe", str(universe_path),
            "--observations", str(observations_path),
            "--output", str(scoring_output_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise SecToScoreError("SEC_TO_SCORE_SCORING_FAILED:" + completed.stderr[-500:])
        score = json.loads(scoring_output_path.read_text(encoding="utf-8"))
    results = validate_score_output(score, information_cutoff, features)
    cutoff = parse_utc(information_cutoff, "SEC_TO_SCORE_INVALID_CUTOFF").isoformat().replace("+00:00", "Z")
    vintage = {
        "information_cutoff": cutoff,
        "generated_at": cutoff,
        "results": results,
        "lineage": {
            "pipeline_version": PIPELINE_VERSION,
            "snapshot_file_sha256": file_sha256(snapshot_path),
            "snapshot_payload_sha256": certification["snapshot_payload_sha256"],
            "raw_content_sha256": certification["raw_content_sha256"],
            "identifier_registry_sha256": registry_hash,
            "feature_definitions_sha256": file_sha256(feature_definitions_path),
            "fundamental_feature_output_sha256": features["output_sha256"],
            "scoring_config_sha256": file_sha256(scoring_config_path),
            "universe_sha256": file_sha256(universe_path),
            "scoring_output_sha256": canonical_hash(score),
        },
        "certification": certification,
        "safety_boundary": {
            "portfolio_consumption": False,
            "dca_consumption": False,
            "dashboard_recommendation": False,
        },
    }
    envelope = {"schema_version": "1.0.0", "vintages": [vintage]}
    envelope["output_sha256"] = canonical_hash(envelope)
    return envelope


def main() -> int:
    parser = argparse.ArgumentParser(description="Run certified SEC-to-score pilot pipeline")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--identifier-registry", required=True)
    parser.add_argument("--feature-definitions", required=True)
    parser.add_argument("--scoring-config", required=True)
    parser.add_argument("--universe", required=True)
    parser.add_argument("--information-cutoff", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = run_pipeline(
            snapshot_path=args.snapshot,
            identifier_registry_path=args.identifier_registry,
            feature_definitions_path=args.feature_definitions,
            scoring_config_path=args.scoring_config,
            universe_path=args.universe,
            information_cutoff=args.information_cutoff,
        )
    except (SecToScoreError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": "completed_certified_score_vintage", "output": args.output}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
