"""Fail-closed validation architecture for production data integration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any
import hashlib
import json
import re

VALIDATION_VERSION = "1.0.0"
DEFAULT_REQUIRED_PROVENANCE_FIELDS = ("source_reference", "retrieval_method", "license")
ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9_.:-]{0,63}$")


def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()).hexdigest()


def parse_utc(value: Any, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"MISSING_{field.upper()}")
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"INVALID_{field.upper()}")
        return None
    if dt.tzinfo is None:
        errors.append(f"TIMEZONE_REQUIRED_{field.upper()}")
        return None
    if dt.utcoffset() != timedelta(0):
        errors.append(f"NON_UTC_{field.upper()}")
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class ValidationResult:
    status: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    fingerprint: str
    schema_version: str = VALIDATION_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "errors": list(self.errors), "warnings": list(self.warnings), "fingerprint": self.fingerprint, "schema_version": self.schema_version}


def validation_result(errors: list[str], warnings: list[str], context: Any) -> ValidationResult:
    status = "FAIL_CLOSED" if errors else ("WARN" if warnings else "PASS")
    fingerprint = canonical_hash({"errors": sorted(errors), "warnings": sorted(warnings), "context": context, "version": VALIDATION_VERSION})
    return ValidationResult(status, tuple(sorted(set(errors))), tuple(sorted(set(warnings))), fingerprint)


def validation_settings(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    required = tuple(config.get("required_provenance_fields", DEFAULT_REQUIRED_PROVENANCE_FIELDS))
    return {
        "required_provenance_fields": required,
        "max_staleness_days": int(config.get("max_staleness_days", 7)),
    }


def _natural_key(row: dict[str, Any], fields: tuple[str, ...], row_number: int, errors: list[str]) -> str | None:
    if not fields:
        errors.append("NATURAL_KEY_FIELDS_REQUIRED")
        return None
    values = []
    for field in fields:
        if field not in row or row[field] in (None, ""):
            errors.append(f"ROW_{row_number}_MISSING_NATURAL_KEY_{field.upper()}")
            return None
        values.append(row[field])
    return canonical_hash(values)


def validate_provider_result(
    result: Any,
    *,
    cutoff_timestamp: str | None = None,
    max_staleness_days: int | None = None,
    required_fields: tuple[str, ...] = (),
    natural_key_fields: tuple[str, ...] = ("id",),
    validation_config: dict[str, Any] | None = None,
) -> ValidationResult:
    settings = validation_settings(validation_config)
    staleness_days = settings["max_staleness_days"] if max_staleness_days is None else max_staleness_days
    required_provenance_fields = settings["required_provenance_fields"]
    errors: list[str] = []
    warnings: list[str] = []
    rows = list(getattr(result, "rows", ()) or ())

    acquisition = parse_utc(getattr(result, "acquisition_timestamp", None), "acquisition_timestamp", errors)
    effective = parse_utc(getattr(result, "effective_timestamp", None), "effective_timestamp", errors)
    publication = parse_utc(getattr(result, "publication_timestamp", None), "publication_timestamp", errors) if getattr(result, "publication_timestamp", None) else None
    cutoff = parse_utc(cutoff_timestamp, "cutoff_timestamp", errors) if cutoff_timestamp else acquisition

    for field in ("provider_id", "vendor", "dataset_type", "schema_version"):
        if not getattr(result, field, None):
            errors.append(f"MISSING_{field.upper()}")
    if getattr(result, "schema_version", None) != VALIDATION_VERSION:
        errors.append("SCHEMA_VERSION_MISMATCH")

    provenance = getattr(result, "provenance", None)
    if not isinstance(provenance, dict):
        errors.append("MISSING_OR_INVALID_PROVENANCE")
    else:
        missing = [field for field in required_provenance_fields if provenance.get(field) in (None, "")]
        if missing:
            errors.extend(f"MISSING_PROVENANCE_{field.upper()}" for field in missing)
            errors.append("MISSING_OR_INVALID_PROVENANCE")

    if acquisition and effective and effective > acquisition:
        errors.append("EFFECTIVE_AFTER_ACQUISITION")
    if publication and acquisition and publication > acquisition:
        errors.append("PUBLICATION_AFTER_ACQUISITION")
    if publication and effective and publication < effective:
        errors.append("PUBLICATION_BEFORE_EFFECTIVE")
    if cutoff:
        for label, dt in (("ACQUISITION", acquisition), ("EFFECTIVE", effective), ("PUBLICATION", publication)):
            if dt and dt > cutoff:
                errors.append(f"FUTURE_DATED_{label}")
        if effective and cutoff - effective > timedelta(days=staleness_days):
            errors.append("STALE_DATA")

    seen_keys: set[str] = set()
    for row_number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            errors.append(f"ROW_{row_number}_NOT_OBJECT")
            continue
        for field in required_fields:
            if row.get(field) in (None, ""):
                errors.append(f"ROW_{row_number}_MISSING_{field.upper()}")
        key = _natural_key(row, natural_key_fields, row_number, errors)
        if key is not None:
            if key in seen_keys:
                errors.append("DUPLICATE_NATURAL_KEY")
            seen_keys.add(key)
        identifier = row.get("security_id") or row.get("ticker") or row.get("id")
        if identifier is not None and not ID_RE.match(str(identifier)):
            errors.append("MALFORMED_IDENTIFIER")

    return validation_result(
        errors,
        warnings,
        {"provider": getattr(result, "provider_id", None), "rows": len(rows), "natural_key_fields": natural_hashable(natural_key_fields), "provenance_fields": required_provenance_fields},
    )


def natural_hashable(fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(fields)


def validate_config(config: dict[str, Any], allowed_keys: set[str]) -> ValidationResult:
    errors: list[str] = []
    if set(config) - allowed_keys:
        errors.append("UNKNOWN_CONFIG_SETTING")
    if not config.get("schema_version") or not config.get("config_version"):
        errors.append("MISSING_CONFIG_VERSION")
    return validation_result(errors, [], config)
