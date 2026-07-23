"""Deterministic Decision Journal audit layer for Winner Tilt AI.

The journal records evidence and displayed decisions without calling or mutating
frozen scoring, portfolio, backtest, or research engines.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

CONTRACT_VERSION = "winner-tilt-decision-journal-v1.0"
DECISION_TYPES = {
    "monthly_score_review",
    "semiannual_rebalance",
    "dca_allocation",
    "backtest_validation",
    "research_context_publication",
    "dashboard_snapshot_publication",
}
REQUIRED_FIELDS = [
    "journal_record_id",
    "run_id",
    "decision_type",
    "decision_timestamp_utc",
    "effective_date",
    "as_of_date",
    "system_identifiers",
    "config_identifiers",
    "source_snapshot_identifiers",
    "universe_snapshot_ref",
    "score_run_ref",
    "validation_status",
    "synthetic_prototype",
    "input_data_cutoff_utc",
    "selected_holdings",
    "reserves",
    "ranks_and_scores",
    "portfolio_weights",
    "dca_allocation",
    "exits",
    "entries",
    "turnover",
    "warnings",
    "rationale_evidence_refs",
    "non_interference_attestation",
]
REFERENCE_FIELDS = [
    "universe_snapshot_ref",
    "score_run_ref",
    "portfolio_run_ref",
    "backtest_run_ref",
    "research_run_ref",
    "dashboard_report_ref",
]

class JournalValidationError(ValueError):
    """Raised when a journal record fails closed."""


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record_hash(record: dict[str, Any]) -> str:
    body = copy.deepcopy(record)
    body.pop("immutable_record_hash", None)
    return sha256_text(canonical_json(body))


def attach_record_hash(record: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(record)
    out["immutable_record_hash"] = record_hash(out)
    return out


def _parse_dt(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise JournalValidationError(f"{field} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise JournalValidationError(f"{field} is invalid: {value}") from exc


def _validate_ref(ref: Any, field: str, cutoff: datetime) -> None:
    if ref is None:
        return
    if not isinstance(ref, dict):
        raise JournalValidationError(f"{field} must be an object")
    path = ref.get("path")
    if not path or Path(str(path)).is_absolute():
        raise JournalValidationError(f"{field}.path must be repository-relative")
    if not ref.get("sha256"):
        raise JournalValidationError(f"{field}.sha256 is required")
    snapshot_ts = ref.get("snapshot_timestamp_utc")
    if not snapshot_ts:
        raise JournalValidationError(f"{field}.snapshot_timestamp_utc is required")
    if _parse_dt(snapshot_ts, f"{field}.snapshot_timestamp_utc") > cutoff:
        raise JournalValidationError(f"{field} is future-dated relative to input_data_cutoff_utc")
    run_id = ref.get("run_id")
    if run_id is not None and not isinstance(run_id, str):
        raise JournalValidationError(f"{field}.run_id must be a string when present")


def validate_record(record: dict[str, Any]) -> None:
    missing = [f for f in REQUIRED_FIELDS if f not in record]
    if missing:
        raise JournalValidationError(f"missing required fields: {', '.join(missing)}")
    if record.get("contract_version") != CONTRACT_VERSION:
        raise JournalValidationError("unsupported or missing contract_version")
    if record["decision_type"] not in DECISION_TYPES:
        raise JournalValidationError(f"unsupported decision_type: {record['decision_type']}")
    decision_ts = _parse_dt(record["decision_timestamp_utc"], "decision_timestamp_utc")
    cutoff = _parse_dt(record["input_data_cutoff_utc"], "input_data_cutoff_utc")
    if cutoff > decision_ts:
        raise JournalValidationError("input_data_cutoff_utc cannot be after decision_timestamp_utc")
    for field in ("effective_date", "as_of_date"):
        if not isinstance(record[field], str) or len(record[field]) != 10:
            raise JournalValidationError(f"{field} must be YYYY-MM-DD")
    for field in REFERENCE_FIELDS:
        required = field in {"universe_snapshot_ref", "score_run_ref"}
        if required and not record.get(field):
            raise JournalValidationError(f"{field} is required")
        _validate_ref(record.get(field), field, cutoff)
    for name in ("system_identifiers", "config_identifiers", "source_snapshot_identifiers", "non_interference_attestation"):
        if not isinstance(record[name], dict) or not record[name]:
            raise JournalValidationError(f"{name} must be a non-empty object")
    for name in ("selected_holdings", "reserves", "ranks_and_scores", "portfolio_weights", "dca_allocation", "exits", "entries", "warnings", "rationale_evidence_refs"):
        if not isinstance(record[name], list):
            raise JournalValidationError(f"{name} must be a list")
    if record["synthetic_prototype"] and not any("not investment evidence" in str(w) for w in record["warnings"]):
        raise JournalValidationError("synthetic/prototype records must warn they are not investment evidence")
    if not all(record["non_interference_attestation"].get(k) is False for k in ("scoring_modified", "portfolio_modified", "backtest_modified", "research_modified", "dashboard_created_record")):
        raise JournalValidationError("non-interference attestation must explicitly confirm no frozen-engine/dashboard mutations")
    expected = record_hash(record)
    if record.get("immutable_record_hash") and record["immutable_record_hash"] != expected:
        raise JournalValidationError("immutable_record_hash does not match canonical record")


def file_ref(path: str | Path, *, root: Path, run_id: str | None = None, snapshot_timestamp_utc: str) -> dict[str, Any]:
    rel = Path(path)
    if rel.is_absolute():
        raise JournalValidationError(f"journal paths must be repository-relative: {path}")
    raw = (root / rel).read_bytes()
    out = {"path": str(rel), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "snapshot_timestamp_utc": snapshot_timestamp_utc}
    if run_id:
        out["run_id"] = run_id
    return out


def construct_record(*, decision_type: str, run_id: str, decision_timestamp_utc: str, effective_date: str, as_of_date: str,
                     input_data_cutoff_utc: str, system_identifiers: dict[str, Any], config_identifiers: dict[str, Any],
                     source_snapshot_identifiers: dict[str, Any], universe_snapshot_ref: dict[str, Any], score_run_ref: dict[str, Any],
                     portfolio_run_ref: dict[str, Any] | None = None, backtest_run_ref: dict[str, Any] | None = None,
                     research_run_ref: dict[str, Any] | None = None, dashboard_report_ref: dict[str, Any] | None = None,
                     score_run: dict[str, Any] | None = None, portfolio_run: dict[str, Any] | None = None,
                     backtest_run: dict[str, Any] | None = None, research_run: dict[str, Any] | None = None,
                     validation_status: str = "VALIDATION_ONLY", synthetic_prototype: bool = True,
                     warnings: list[str] | None = None, rationale_evidence_refs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    score = copy.deepcopy(score_run or {})
    portfolio = copy.deepcopy(portfolio_run or {})
    backtest = copy.deepcopy(backtest_run or {})
    research = copy.deepcopy(research_run or {})
    rows = sorted(score.get("results", []), key=lambda r: r.get("overall_rank") or 999999)[:30]
    holdings = copy.deepcopy(portfolio.get("holdings", []))
    reserves = copy.deepcopy(portfolio.get("reserves", []))
    dca_map = portfolio.get("dca_allocation", {})
    if not holdings and rows and decision_type == "monthly_score_review":
        holdings = []
    entries = [h for h in holdings if h.get("decision") in {"BUY", "HOLD"}]
    warn = list(warnings or [])
    if synthetic_prototype:
        warn.append("Synthetic/prototype validation-only journal record; not investment evidence.")
    record = {
        "contract_version": CONTRACT_VERSION,
        "journal_record_id": f"DJ-{run_id}-{decision_type}",
        "run_id": run_id,
        "decision_type": decision_type,
        "decision_timestamp_utc": decision_timestamp_utc,
        "effective_date": effective_date,
        "as_of_date": as_of_date,
        "system_identifiers": copy.deepcopy(system_identifiers),
        "config_identifiers": copy.deepcopy(config_identifiers),
        "source_snapshot_identifiers": copy.deepcopy(source_snapshot_identifiers),
        "universe_snapshot_ref": copy.deepcopy(universe_snapshot_ref),
        "score_run_ref": copy.deepcopy(score_run_ref),
        "portfolio_run_ref": copy.deepcopy(portfolio_run_ref),
        "backtest_run_ref": copy.deepcopy(backtest_run_ref),
        "research_run_ref": copy.deepcopy(research_run_ref),
        "dashboard_report_ref": copy.deepcopy(dashboard_report_ref),
        "validation_status": validation_status,
        "synthetic_prototype": synthetic_prototype,
        "input_data_cutoff_utc": input_data_cutoff_utc,
        "selected_holdings": holdings,
        "reserves": reserves,
        "ranks_and_scores": [{"security_id": r.get("security_id"), "ticker": r.get("ticker"), "overall_rank": r.get("overall_rank"), "total_score": r.get("total_score")} for r in rows],
        "portfolio_weights": [{"security_id": h.get("security_id"), "weight": h.get("weight")} for h in holdings],
        "dca_allocation": [{"security_id": sid, "allocation": amount} for sid, amount in sorted(dca_map.items())],
        "exits": copy.deepcopy(portfolio.get("exits", [])),
        "entries": entries,
        "turnover": portfolio.get("portfolio_summary", {}).get("one_way_turnover", backtest.get("turnover")),
        "warnings": sorted(set(warn)),
        "rationale_evidence_refs": copy.deepcopy(rationale_evidence_refs or []),
        "research_context_summary": {"run_status": research.get("run_status"), "accepted_event_count": len(research.get("accepted_events", []))} if research else {},
        "non_interference_attestation": {"scoring_modified": False, "portfolio_modified": False, "backtest_modified": False, "research_modified": False, "dashboard_created_record": False},
    }
    out = attach_record_hash(record)
    validate_record(out)
    return out


class JournalStore:
    def __init__(self, path: str | Path):
        p = Path(path)
        if p.is_absolute():
            raise JournalValidationError("journal store path must be repository-relative")
        self.path = p

    def append(self, record: dict[str, Any]) -> None:
        validate_record(record)
        existing = self.load()
        ids = {r["journal_record_id"] for r in existing}
        hashes = {r["immutable_record_hash"] for r in existing}
        if record["journal_record_id"] in ids or record["immutable_record_hash"] in hashes:
            raise JournalValidationError("duplicate journal record detected")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(canonical_json(record) + "\n")

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records = []
        for line_no, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            rec = json.loads(line)
            validate_record(rec)
            records.append(rec)
        seen_ids = set(); seen_hashes = set()
        for rec in records:
            if rec["journal_record_id"] in seen_ids or rec["immutable_record_hash"] in seen_hashes:
                raise JournalValidationError("duplicate journal record detected on reload")
            seen_ids.add(rec["journal_record_id"]); seen_hashes.add(rec["immutable_record_hash"])
        return records

    def verify_integrity(self) -> dict[str, Any]:
        records = self.load()
        chain = sha256_text("\n".join(r["immutable_record_hash"] for r in records)) if records else None
        return {"valid": True, "record_count": len(records), "journal_chain_sha256": chain}
