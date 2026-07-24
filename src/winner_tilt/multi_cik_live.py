"""Bounded multi-CIK authorization, aggregation, and live artifact certification.

This layer reuses the proven M17 contracts while preventing the integration
regressions discovered during the single-CIK pilot: snapshot discovery is
recursive, the canonical universe remains repository-relative, aggregate
lineage is hash-addressed, and insufficient portfolio coverage remains a
non-executable research outcome rather than a rules relaxation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

AUTHORIZATION_PHRASE = "AUTHORIZE_MULTI_CIK_SEC_SHADOW_RESEARCH_ONLY"
ENGINE_VERSION = "1.0.0"
MAX_CIKS = 3
PROVIDER_ID = "sec-edgar-companyfacts"


class MultiCikLiveError(ValueError):
    """Raised whenever a multi-CIK live gate fails closed."""


def _hash_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _parse_utc(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise MultiCikLiveError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MultiCikLiveError(code) from exc
    if parsed.tzinfo is None:
        raise MultiCikLiveError(code)
    return parsed.astimezone(timezone.utc)


def load_active_registry(path: str | Path) -> dict[str, dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    active: dict[str, dict[str, str]] = {}
    securities: set[str] = set()
    for row in rows:
        if row.get("status") != "ACTIVE":
            continue
        cik = str(row.get("cik", "")).strip().zfill(10)
        security_id = str(row.get("security_id", "")).strip()
        ticker = str(row.get("ticker", "")).strip()
        if not cik.isdigit() or len(cik) != 10 or not security_id or not ticker:
            raise MultiCikLiveError("MULTI_CIK_REGISTRY_ROW_INVALID")
        if cik in active or security_id in securities:
            raise MultiCikLiveError("MULTI_CIK_REGISTRY_NOT_ONE_TO_ONE")
        active[cik] = dict(row, cik=cik)
        securities.add(security_id)
    if not active:
        raise MultiCikLiveError("MULTI_CIK_REGISTRY_EMPTY")
    return active


def parse_authorized_ciks(value: str, *, registry_path: str | Path, authorization: str,
                          maximum: int = MAX_CIKS) -> tuple[str, ...]:
    if authorization != AUTHORIZATION_PHRASE:
        raise MultiCikLiveError("MULTI_CIK_AUTHORIZATION_REQUIRED")
    raw = [item.strip() for item in value.split(",") if item.strip()]
    normalized = tuple(item.zfill(10) for item in raw)
    if not normalized:
        raise MultiCikLiveError("MULTI_CIK_LIST_REQUIRED")
    if len(normalized) > maximum:
        raise MultiCikLiveError("MULTI_CIK_REQUEST_LIMIT_EXCEEDED")
    if any(not cik.isdigit() or len(cik) != 10 for cik in normalized):
        raise MultiCikLiveError("MULTI_CIK_FORMAT_INVALID")
    if len(set(normalized)) != len(normalized):
        raise MultiCikLiveError("MULTI_CIK_DUPLICATE_REQUEST")
    registry = load_active_registry(registry_path)
    missing = [cik for cik in normalized if cik not in registry]
    if missing:
        raise MultiCikLiveError("MULTI_CIK_UNREGISTERED:" + ",".join(missing))
    return normalized


def build_authorization_gate(*, ciks: str, authorization: str, registry_path: str | Path) -> dict[str, Any]:
    approved = parse_authorized_ciks(ciks, registry_path=registry_path, authorization=authorization)
    registry = load_active_registry(registry_path)
    gate = {
        "engine_version": ENGINE_VERSION,
        "status": "AUTHORIZED_MULTI_CIK_RESEARCH_ONLY",
        "authorization_phrase": AUTHORIZATION_PHRASE,
        "approved_ciks": list(approved),
        "request_count": len(approved),
        "maximum_request_count": MAX_CIKS,
        "approved_securities": [
            {"cik": cik, "security_id": registry[cik]["security_id"], "ticker": registry[cik]["ticker"]}
            for cik in approved
        ],
        "identifier_registry_sha256": _hash_bytes(Path(registry_path)),
        "execution_boundary": {
            "broker_connected": False,
            "orders_created": False,
            "orders_executed": False,
            "automatic_dca": False,
            "automatic_exits": False,
        },
    }
    gate["gate_sha256"] = _canonical_hash(gate)
    return gate


def _discover_snapshots(snapshot_dir: Path) -> dict[str, Path]:
    discovered: dict[str, Path] = {}
    for path in sorted(snapshot_dir.rglob("CIK*.json")):
        name = path.stem
        cik = name[3:] if name.startswith("CIK") else ""
        if not cik.isdigit() or len(cik) != 10:
            raise MultiCikLiveError("MULTI_CIK_SNAPSHOT_NAME_INVALID")
        if cik in discovered:
            raise MultiCikLiveError("MULTI_CIK_DUPLICATE_SNAPSHOT:" + cik)
        discovered[cik] = path
    return discovered


def build_aggregate_snapshot(*, gate: Mapping[str, Any], snapshot_dir: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    expected = tuple(gate.get("approved_ciks", []))
    if not expected or gate.get("status") != "AUTHORIZED_MULTI_CIK_RESEARCH_ONLY":
        raise MultiCikLiveError("MULTI_CIK_GATE_INVALID")
    root = Path(snapshot_dir)
    discovered = _discover_snapshots(root)
    if set(discovered) != set(expected):
        missing = sorted(set(expected) - set(discovered))
        extra = sorted(set(discovered) - set(expected))
        raise MultiCikLiveError(
            "MULTI_CIK_SNAPSHOT_SET_MISMATCH:missing=" + ",".join(missing) + ";extra=" + ",".join(extra)
        )

    entries: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    row_ids: set[str] = set()
    acquisitions: list[datetime] = []
    for cik in expected:
        path = discovered[cik]
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("dataset_type") != "fundamentals" or payload.get("provider_id") != PROVIDER_ID:
            raise MultiCikLiveError("MULTI_CIK_SNAPSHOT_CONTRACT_INVALID:" + cik)
        if payload.get("pilot_tag") != "ingest_only_no_downstream_consumption":
            raise MultiCikLiveError("MULTI_CIK_SNAPSHOT_PILOT_TAG_REQUIRED:" + cik)
        provenance = payload.get("provenance")
        if not isinstance(provenance, Mapping) or provenance.get("raw_payload_retained") is not False:
            raise MultiCikLiveError("MULTI_CIK_SNAPSHOT_PROVENANCE_INVALID:" + cik)
        acquisition = _parse_utc(payload.get("acquisition_timestamp"), "MULTI_CIK_ACQUISITION_INVALID")
        acquisitions.append(acquisition)
        source_rows = payload.get("rows")
        if not isinstance(source_rows, list) or not source_rows:
            raise MultiCikLiveError("MULTI_CIK_SNAPSHOT_ROWS_REQUIRED:" + cik)
        for source in source_rows:
            if str(source.get("cik", "")).zfill(10) != cik:
                raise MultiCikLiveError("MULTI_CIK_ROW_CIK_MISMATCH:" + cik)
            row_id = str(source.get("id", ""))
            if not row_id or row_id in row_ids:
                raise MultiCikLiveError("MULTI_CIK_DUPLICATE_ROW_ID")
            row_ids.add(row_id)
            rows.append(dict(source))
        entries.append({
            "cik": cik,
            "path": str(path.relative_to(root)),
            "sha256": _hash_bytes(path),
            "row_count": len(source_rows),
            "acquisition_timestamp": acquisition.isoformat().replace("+00:00", "Z"),
            "raw_content_sha256": provenance.get("raw_content_sha256"),
        })

    entries.sort(key=lambda item: item["cik"])
    rows.sort(key=lambda row: str(row["id"]))
    manifest = {
        "schema_version": "1.0.0",
        "status": "CERTIFIED_MULTI_CIK_SNAPSHOT_SET",
        "snapshot_count": len(entries),
        "total_row_count": len(rows),
        "approved_ciks": list(expected),
        "entries": entries,
        "gate_sha256": gate.get("gate_sha256"),
    }
    manifest["manifest_sha256"] = _canonical_hash(manifest)
    aggregate = {
        "dataset_type": "fundamentals",
        "provider_id": PROVIDER_ID,
        "acquisition_timestamp": max(acquisitions).isoformat().replace("+00:00", "Z"),
        "rows": rows,
        "provenance": {
            "raw_payload_retained": False,
            "raw_content_sha256": _canonical_hash([entry["raw_content_sha256"] for entry in entries]),
            "aggregate_manifest_sha256": manifest["manifest_sha256"],
        },
        "pilot_tag": "ingest_only_no_downstream_consumption",
        "validation_state": "aggregate_recertification_required",
        "source_snapshot_manifest": manifest,
    }
    return aggregate, manifest


def finalize_live_bundle(*, gate: Mapping[str, Any], aggregate_path: str | Path,
                         aggregate_manifest: Mapping[str, Any], shadow_manifest: Mapping[str, Any]) -> dict[str, Any]:
    boundary = shadow_manifest.get("execution_boundary")
    if not isinstance(boundary, Mapping) or any(value is not False for value in boundary.values()):
        raise MultiCikLiveError("MULTI_CIK_EXECUTION_BOUNDARY_FAILED")
    if shadow_manifest.get("broker_integration_enabled") is not False:
        raise MultiCikLiveError("MULTI_CIK_BROKER_FLAG_INVALID")
    aggregate = json.loads(Path(aggregate_path).read_text(encoding="utf-8"))
    embedded = aggregate.get("source_snapshot_manifest")
    if embedded != aggregate_manifest:
        raise MultiCikLiveError("MULTI_CIK_MANIFEST_EMBED_MISMATCH")
    result = {
        "engine_version": ENGINE_VERSION,
        "status": "COMPLETED_AUTHORIZED_MULTI_CIK_SHADOW_RESEARCH_ONLY",
        "approved_ciks": list(gate["approved_ciks"]),
        "snapshot_count": aggregate_manifest["snapshot_count"],
        "aggregate_snapshot_sha256": _hash_bytes(Path(aggregate_path)),
        "aggregate_manifest_sha256": aggregate_manifest["manifest_sha256"],
        "shadow_run_manifest_sha256": _canonical_hash(shadow_manifest),
        "execution_boundary": dict(boundary),
        "broker_integration_enabled": False,
    }
    result["output_sha256"] = _canonical_hash(result)
    return result


def _write(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded multi-CIK SEC live research gate")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--ciks", required=True)
    validate.add_argument("--authorization", required=True)
    validate.add_argument("--identifier-registry", required=True)
    validate.add_argument("--output", required=True)
    aggregate = sub.add_parser("aggregate")
    aggregate.add_argument("--gate", required=True)
    aggregate.add_argument("--snapshot-dir", required=True)
    aggregate.add_argument("--snapshot-output", required=True)
    aggregate.add_argument("--manifest-output", required=True)
    finalize = sub.add_parser("finalize")
    finalize.add_argument("--gate", required=True)
    finalize.add_argument("--aggregate-snapshot", required=True)
    finalize.add_argument("--aggregate-manifest", required=True)
    finalize.add_argument("--shadow-manifest", required=True)
    finalize.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            result = build_authorization_gate(ciks=args.ciks, authorization=args.authorization,
                                              registry_path=args.identifier_registry)
            _write(args.output, result)
        elif args.command == "aggregate":
            gate = json.loads(Path(args.gate).read_text(encoding="utf-8"))
            snapshot, manifest = build_aggregate_snapshot(gate=gate, snapshot_dir=args.snapshot_dir)
            _write(args.snapshot_output, snapshot)
            _write(args.manifest_output, manifest)
            result = {"status": "aggregated", "snapshot_count": manifest["snapshot_count"]}
        else:
            gate = json.loads(Path(args.gate).read_text(encoding="utf-8"))
            aggregate_manifest = json.loads(Path(args.aggregate_manifest).read_text(encoding="utf-8"))
            shadow_manifest = json.loads(Path(args.shadow_manifest).read_text(encoding="utf-8"))
            result = finalize_live_bundle(gate=gate, aggregate_path=args.aggregate_snapshot,
                                          aggregate_manifest=aggregate_manifest,
                                          shadow_manifest=shadow_manifest)
            _write(args.output, result)
    except (MultiCikLiveError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
