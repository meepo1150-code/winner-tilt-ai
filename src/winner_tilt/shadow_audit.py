"""Audit certified shadow portfolios through the existing Decision Journal contract."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from winner_tilt.decision_journal import JournalStore, construct_record, file_ref

ENGINE_VERSION = "1.0.0"


class ShadowAuditError(ValueError):
    """Raised when a shadow portfolio cannot be audited safely."""


def _parse_utc(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ShadowAuditError(code)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise ShadowAuditError(code) from exc


def _hash_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_shadow_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("mode") != "SHADOW_RESEARCH_ONLY":
        raise ShadowAuditError("SHADOW_AUDIT_NON_SHADOW_INPUT")
    certification = payload.get("certification")
    if not isinstance(certification, Mapping) or certification.get("status") != "CERTIFIED":
        raise ShadowAuditError("SHADOW_AUDIT_UNCERTIFIED_INPUT")
    boundary = payload.get("execution_boundary")
    required_flags = ("broker_connected", "orders_created", "orders_executed", "automatic_dca", "automatic_exits")
    if not isinstance(boundary, Mapping) or any(boundary.get(flag) is not False for flag in required_flags):
        raise ShadowAuditError("SHADOW_AUDIT_EXECUTABLE_FLAG_DETECTED")
    lineage = payload.get("lineage")
    required_hashes = ("certified_vintage_sha256", "portfolio_config_sha256", "universe_sha256", "portfolio_output_sha256")
    if not isinstance(lineage, Mapping) or any(not isinstance(lineage.get(key), str) or len(lineage[key]) != 64 for key in required_hashes):
        raise ShadowAuditError("SHADOW_AUDIT_LINEAGE_REQUIRED")
    portfolio = payload.get("portfolio")
    if not isinstance(portfolio, Mapping):
        raise ShadowAuditError("SHADOW_AUDIT_PORTFOLIO_REQUIRED")
    holdings = portfolio.get("holdings")
    reserves = portfolio.get("reserves")
    if not isinstance(holdings, list) or not isinstance(reserves, list):
        raise ShadowAuditError("SHADOW_AUDIT_SELECTIONS_REQUIRED")
    ids = [row.get("security_id") for row in holdings + reserves]
    if any(not isinstance(sid, str) or not sid for sid in ids) or len(ids) != len(set(ids)):
        raise ShadowAuditError("SHADOW_AUDIT_DUPLICATE_SELECTION")
    expected = hashlib.sha256(json.dumps(portfolio, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    if lineage["portfolio_output_sha256"] != expected:
        raise ShadowAuditError("SHADOW_AUDIT_PORTFOLIO_HASH_MISMATCH")


def build_shadow_journal_record(*, shadow_path: str | Path, vintage_path: str | Path,
                                universe_path: str | Path, root: str | Path,
                                decision_timestamp_utc: str, run_id: str) -> dict[str, Any]:
    root_path = Path(root)
    shadow_rel = Path(shadow_path)
    vintage_rel = Path(vintage_path)
    universe_rel = Path(universe_path)
    if any(path.is_absolute() for path in (shadow_rel, vintage_rel, universe_rel)):
        raise ShadowAuditError("SHADOW_AUDIT_PATHS_MUST_BE_REPOSITORY_RELATIVE")
    shadow = json.loads((root_path / shadow_rel).read_text(encoding="utf-8"))
    vintage_payload = json.loads((root_path / vintage_rel).read_text(encoding="utf-8"))
    validate_shadow_payload(shadow)
    vintages = vintage_payload.get("vintages")
    if not isinstance(vintages, list) or len(vintages) != 1:
        raise ShadowAuditError("SHADOW_AUDIT_SINGLE_VINTAGE_REQUIRED")
    vintage = vintages[0]
    cutoff = vintage.get("information_cutoff")
    cutoff_dt = _parse_utc(cutoff, "SHADOW_AUDIT_INVALID_CUTOFF")
    decision_dt = _parse_utc(decision_timestamp_utc, "SHADOW_AUDIT_INVALID_DECISION_TIMESTAMP")
    if cutoff_dt > decision_dt:
        raise ShadowAuditError("SHADOW_AUDIT_FUTURE_CUTOFF")
    as_of_date = shadow.get("as_of_date")
    if not isinstance(as_of_date, str) or len(as_of_date) != 10:
        raise ShadowAuditError("SHADOW_AUDIT_INVALID_AS_OF_DATE")
    portfolio = shadow["portfolio"]
    return construct_record(
        decision_type="semiannual_rebalance",
        run_id=run_id,
        decision_timestamp_utc=decision_timestamp_utc,
        effective_date=as_of_date,
        as_of_date=as_of_date,
        input_data_cutoff_utc=cutoff,
        system_identifiers={"shadow_audit_engine_version": ENGINE_VERSION, "shadow_portfolio_engine_version": shadow.get("engine_version")},
        config_identifiers={"portfolio_config_sha256": shadow["lineage"]["portfolio_config_sha256"]},
        source_snapshot_identifiers={"shadow_output_sha256": shadow.get("output_sha256"), "certified_vintage_sha256": shadow["lineage"]["certified_vintage_sha256"]},
        universe_snapshot_ref=file_ref(universe_rel, root=root_path, snapshot_timestamp_utc=cutoff),
        score_run_ref=file_ref(vintage_rel, root=root_path, run_id=run_id, snapshot_timestamp_utc=cutoff),
        portfolio_run_ref=file_ref(shadow_rel, root=root_path, run_id=run_id, snapshot_timestamp_utc=cutoff),
        score_run=vintage,
        portfolio_run=portfolio,
        validation_status="SHADOW_CERTIFIED_RESEARCH_ONLY",
        synthetic_prototype=False,
        warnings=["Shadow portfolio audit only; no broker, order, automatic DCA, or automatic exit action is enabled."],
        rationale_evidence_refs=[{"path": str(shadow_rel), "sha256": _hash_bytes(root_path / shadow_rel)}],
    )


def append_shadow_journal_record(*, journal_path: str | Path, record: Mapping[str, Any]) -> None:
    JournalStore(journal_path).append(dict(record))


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a certified shadow portfolio into the append-only Decision Journal")
    parser.add_argument("--shadow", required=True)
    parser.add_argument("--vintage", required=True)
    parser.add_argument("--universe", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--decision-timestamp", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--journal")
    args = parser.parse_args()
    record = build_shadow_journal_record(
        shadow_path=args.shadow, vintage_path=args.vintage, universe_path=args.universe,
        root=args.root, decision_timestamp_utc=args.decision_timestamp, run_id=args.run_id,
    )
    Path(args.output).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.journal:
        append_shadow_journal_record(journal_path=args.journal, record=record)


if __name__ == "__main__":
    main()
