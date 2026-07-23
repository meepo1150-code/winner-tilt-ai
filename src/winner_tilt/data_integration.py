"""Production data integration validation for Winner Tilt AI.

This module validates externally supplied production data snapshots before they
are used by downstream deterministic engines. It is intentionally ingest-only:
it does not fetch data from networks, alter scoring/portfolio/backtest logic, or
make investment decisions.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ENGINE_VERSION = "1.0.0"
REQUIRED_DATASETS = ("universe", "metrics", "events")
REQUIRED_FIELDS = {
    "universe": ("security_id", "ticker", "name", "sector", "active"),
    "metrics": ("security_id", "metric_id", "as_of_date", "value", "source_name", "source_tier", "ingested_at"),
    "events": ("event_id", "event_type", "security_id", "published_at", "source_name", "source_tier"),
}
SOURCE_TIERS = {"PRIMARY", "REGULATED", "VENDOR", "DERIVED", "UNVERIFIED"}


class DataIntegrationError(ValueError):
    """Raised when production data integration inputs fail closed."""


def canonical_hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def parse_utc(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise DataIntegrationError(f"MISSING_{field.upper()}")
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DataIntegrationError(f"INVALID_{field.upper()}") from exc
    if dt.tzinfo is None:
        raise DataIntegrationError(f"TIMEZONE_REQUIRED_{field.upper()}")
    return dt.astimezone(timezone.utc)


def load_rows(path: str | Path) -> list[dict[str, str]]:
    p = Path(path)
    if p.suffix.lower() == ".json":
        payload = json.loads(p.read_text(encoding="utf-8"))
        rows = payload.get("rows", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise DataIntegrationError(f"JSON_ROWS_MUST_BE_OBJECTS:{p}")
        return [{str(k): "" if v is None else str(v) for k, v in row.items()} for row in rows]
    with p.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def file_snapshot(path: str | Path, *, root: Path) -> dict[str, Any]:
    p = Path(path)
    raw = (root / p).read_bytes() if not p.is_absolute() else p.read_bytes()
    return {"path": str(p), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _missing_required(row: dict[str, Any], dataset: str) -> list[str]:
    return [field for field in REQUIRED_FIELDS[dataset] if row.get(field) in (None, "")]


def _date_key(value: str) -> datetime:
    return datetime.fromisoformat(value.strip() + "T00:00:00+00:00")


def validate_production_snapshot(
    snapshot: dict[str, Iterable[dict[str, Any]]],
    *,
    information_cutoff: str,
    source_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate production universe, metric, and event rows fail-closed.

    Returns a deterministic integration report. Rejected rows are summarized by
    dataset, row number, stable row hash, and validation errors so raw vendor
    payloads do not need to be copied into audit output.
    """
    cutoff = parse_utc(information_cutoff, "information_cutoff")
    missing_datasets = [name for name in REQUIRED_DATASETS if name not in snapshot]
    if missing_datasets:
        raise DataIntegrationError(f"MISSING_DATASETS:{','.join(missing_datasets)}")

    accepted: dict[str, list[dict[str, Any]]] = {name: [] for name in REQUIRED_DATASETS}
    rejected: list[dict[str, Any]] = []
    seen_keys: dict[str, set[str]] = {name: set() for name in REQUIRED_DATASETS}
    active_security_ids: set[str] = set()

    for dataset in REQUIRED_DATASETS:
        rows = list(snapshot[dataset])
        for row_no, row in enumerate(rows, 1):
            errors = [f"MISSING_{field.upper()}" for field in _missing_required(row, dataset)]
            normalized = dict(row)
            if dataset == "universe":
                key = str(row.get("security_id", "")).strip()
                normalized["active"] = str(row.get("active", "")).strip().lower() in {"1", "true", "yes", "y"}
                if normalized["active"]:
                    active_security_ids.add(key)
            elif dataset == "metrics":
                key = "|".join(str(row.get(x, "")).strip() for x in ("security_id", "metric_id", "as_of_date"))
                try:
                    as_of = _date_key(str(row.get("as_of_date", "")))
                    if as_of > cutoff:
                        errors.append("AS_OF_DATE_AFTER_CUTOFF")
                except ValueError:
                    errors.append("INVALID_AS_OF_DATE")
                try:
                    normalized["value"] = float(row.get("value", ""))
                except (TypeError, ValueError):
                    errors.append("INVALID_VALUE")
                try:
                    ingested = parse_utc(str(row.get("ingested_at", "")), "ingested_at")
                    if ingested > cutoff:
                        errors.append("INGESTED_AFTER_CUTOFF")
                except DataIntegrationError as exc:
                    errors.append(str(exc))
            else:
                key = str(row.get("event_id", "")).strip()
                try:
                    published = parse_utc(str(row.get("published_at", "")), "published_at")
                    if published > cutoff:
                        errors.append("PUBLICATION_AFTER_CUTOFF")
                except DataIntegrationError as exc:
                    errors.append(str(exc))

            if dataset in {"metrics", "events"}:
                sid = str(row.get("security_id", "")).strip()
                if sid and sid not in active_security_ids:
                    errors.append("UNKNOWN_OR_INACTIVE_SECURITY_ID")
                if row.get("source_tier") not in SOURCE_TIERS:
                    errors.append("INVALID_SOURCE_TIER")
            if key in seen_keys[dataset]:
                errors.append("DUPLICATE_NATURAL_KEY")
            if errors:
                rejected.append({"dataset": dataset, "row_number": row_no, "row_sha256": canonical_hash(row), "errors": sorted(set(errors))})
                continue
            seen_keys[dataset].add(key)
            normalized["integration_row_sha256"] = canonical_hash(normalized)
            accepted[dataset].append(normalized)

    counts = {name: {"accepted": len(accepted[name])} for name in REQUIRED_DATASETS}
    for name in REQUIRED_DATASETS:
        counts[name]["rejected"] = sum(1 for row in rejected if row["dataset"] == name)
    status = "PASS" if not rejected else "FAIL_CLOSED"
    report = {
        "engine_version": ENGINE_VERSION,
        "run_status": status,
        "information_cutoff": cutoff.isoformat().replace("+00:00", "Z"),
        "source_manifest": source_manifest or {},
        "counts": counts,
        "accepted_security_ids": sorted(active_security_ids),
        "rejected_rows": rejected,
        "non_interference": {"scoring_modified": False, "portfolio_modified": False, "backtest_modified": False, "research_modified": False},
    }
    report["output_sha256"] = canonical_hash(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--information-cutoff", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path.cwd()
    snapshot = {"universe": load_rows(args.universe), "metrics": load_rows(args.metrics), "events": load_rows(args.events)}
    manifest = {name: file_snapshot(getattr(args, name), root=root) for name in REQUIRED_DATASETS}
    out = validate_production_snapshot(snapshot, information_cutoff=args.information_cutoff, source_manifest=manifest)
    Path(args.output).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
