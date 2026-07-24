"""Explicit authorization gate for the live SEC-to-shadow pilot.

This module contains no HTTP client and no investment logic. It validates a manual
operator authorization before the existing SEC ingest and shadow pipelines run,
and can certify the resulting artifact bundle afterwards.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENGINE_VERSION = "1.0.0"
AUTHORIZATION_PHRASE = "AUTHORIZE_LIVE_SEC_SHADOW_RESEARCH_ONLY"


class LiveShadowGateError(ValueError):
    """Raised when live shadow authorization fails closed."""


def _relative(path: str | Path, code: str) -> Path:
    value = Path(path)
    if value.is_absolute() or ".." in value.parts:
        raise LiveShadowGateError(code)
    return value


def _normalize_cik(value: str) -> str:
    digits = str(value).strip()
    if not digits.isdigit() or len(digits) > 10:
        raise LiveShadowGateError("LIVE_SHADOW_INVALID_CIK")
    return digits.zfill(10)


def validate_authorization(*, cik: str, authorization: str, identifier_registry_path: str | Path) -> dict[str, Any]:
    normalized = _normalize_cik(cik)
    if authorization != AUTHORIZATION_PHRASE:
        raise LiveShadowGateError("LIVE_SHADOW_AUTHORIZATION_REQUIRED")
    registry_path = Path(identifier_registry_path)
    if not registry_path.is_file():
        raise LiveShadowGateError("LIVE_SHADOW_IDENTIFIER_REGISTRY_MISSING")
    with registry_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    matches = [row for row in rows if _normalize_cik(row.get("cik", "")) == normalized and row.get("status") == "ACTIVE"]
    if len(matches) != 1:
        raise LiveShadowGateError("LIVE_SHADOW_CIK_NOT_ACTIVE_AND_UNIQUE")
    row = matches[0]
    return {
        "status": "AUTHORIZED_LIVE_FETCH",
        "engine_version": ENGINE_VERSION,
        "cik": normalized,
        "security_id": row.get("security_id"),
        "ticker": row.get("ticker"),
        "research_only": True,
        "downstream_execution_enabled": False,
    }


def select_single_snapshot(snapshot_dir: str | Path) -> Path:
    root = Path(snapshot_dir)
    candidates = sorted(path for path in root.glob("*.json") if path.is_file())
    if len(candidates) != 1:
        raise LiveShadowGateError("LIVE_SHADOW_SINGLE_SNAPSHOT_REQUIRED")
    return candidates[0]


def certify_bundle(*, gate: dict[str, Any], snapshot_path: str | Path, shadow_manifest_path: str | Path) -> dict[str, Any]:
    if gate.get("status") != "AUTHORIZED_LIVE_FETCH" or gate.get("research_only") is not True:
        raise LiveShadowGateError("LIVE_SHADOW_INVALID_GATE")
    snapshot = Path(snapshot_path)
    manifest_path = Path(shadow_manifest_path)
    if not snapshot.is_file() or not manifest_path.is_file():
        raise LiveShadowGateError("LIVE_SHADOW_ARTIFACT_MISSING")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    boundary = manifest.get("execution_boundary")
    if not isinstance(boundary, dict) or any(value is not False for value in boundary.values()):
        raise LiveShadowGateError("LIVE_SHADOW_EXECUTION_BOUNDARY_FAILED")
    if manifest.get("broker_integration_enabled") is not False:
        raise LiveShadowGateError("LIVE_SHADOW_BROKER_BOUNDARY_FAILED")
    result = {
        "engine_version": ENGINE_VERSION,
        "status": "COMPLETED_AUTHORIZED_LIVE_SHADOW_RESEARCH_ONLY",
        "authorization": gate,
        "completed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "snapshot_path": str(snapshot),
        "snapshot_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        "shadow_manifest_path": str(manifest_path),
        "shadow_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "execution_boundary": dict(boundary),
        "broker_integration_enabled": False,
        "orders_created": False,
        "orders_executed": False,
    }
    return result


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Authorize or certify a live SEC-to-shadow research pilot")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--cik", required=True)
    validate.add_argument("--authorization", required=True)
    validate.add_argument("--identifier-registry", required=True)
    validate.add_argument("--output", required=True)
    finalize = sub.add_parser("finalize")
    finalize.add_argument("--gate", required=True)
    finalize.add_argument("--snapshot-dir", required=True)
    finalize.add_argument("--shadow-manifest", required=True)
    finalize.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "validate":
        result = validate_authorization(cik=args.cik, authorization=args.authorization,
                                        identifier_registry_path=args.identifier_registry)
    else:
        gate = json.loads(Path(args.gate).read_text(encoding="utf-8"))
        result = certify_bundle(gate=gate, snapshot_path=select_single_snapshot(args.snapshot_dir),
                                shadow_manifest_path=args.shadow_manifest)
    _write(Path(args.output), result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
