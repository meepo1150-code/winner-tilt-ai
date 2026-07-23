"""Fail-closed validation architecture for production data integration."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any
import hashlib, json, re

VALIDATION_VERSION="1.0.0"
STATUSES={"PASS","WARN","FAIL_CLOSED"}
ID_RE=re.compile(r"^[A-Z0-9][A-Z0-9_.:-]{0,63}$")

def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=False, default=str).encode()).hexdigest()

def parse_utc(value: Any, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value,str) or not value.strip(): errors.append(f"MISSING_{field.upper()}"); return None
    try: dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError: errors.append(f"INVALID_{field.upper()}"); return None
    if dt.tzinfo is None: errors.append(f"TIMEZONE_REQUIRED_{field.upper()}"); return None
    if dt.utcoffset()!=timedelta(0): errors.append(f"NON_UTC_{field.upper()}")
    return dt.astimezone(timezone.utc)

@dataclass(frozen=True)
class ValidationResult:
    status: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    fingerprint: str
    schema_version: str = VALIDATION_VERSION
    def to_dict(self) -> dict[str, Any]: return self.__dict__ | {"errors":list(self.errors), "warnings":list(self.warnings)}

def validation_result(errors: list[str], warnings: list[str], context: Any) -> ValidationResult:
    status="FAIL_CLOSED" if errors else ("WARN" if warnings else "PASS")
    fp=canonical_hash({"errors":sorted(errors),"warnings":sorted(warnings),"context":context,"version":VALIDATION_VERSION})
    return ValidationResult(status, tuple(sorted(set(errors))), tuple(sorted(set(warnings))), fp)

def validate_provider_result(result: Any, *, cutoff_timestamp: str | None=None, max_staleness_days: int=7, required_fields: tuple[str,...]=()) -> ValidationResult:
    errors=[]; warnings=[]; rows=list(getattr(result,"rows",()) or ())
    acq=parse_utc(getattr(result,"acquisition_timestamp",None),"acquisition_timestamp",errors)
    eff=parse_utc(getattr(result,"effective_timestamp",None),"effective_timestamp",errors)
    pub=parse_utc(getattr(result,"publication_timestamp",None),"publication_timestamp",errors) if getattr(result,"publication_timestamp",None) else None
    cutoff=parse_utc(cutoff_timestamp,"cutoff_timestamp",errors) if cutoff_timestamp else acq
    for name in ("provider_id","vendor","dataset_type","schema_version"):
        if not getattr(result,name,None): errors.append(f"MISSING_{name.upper()}")
    if getattr(result,"schema_version",None)!="1.0.0": errors.append("SCHEMA_VERSION_MISMATCH")
    prov=getattr(result,"provenance",None)
    if not isinstance(prov,dict) or not prov.get("source_reference") or not prov.get("retrieval_method"): errors.append("MISSING_OR_INVALID_PROVENANCE")
    if acq and eff and eff>acq: errors.append("EFFECTIVE_AFTER_ACQUISITION")
    if pub and acq and pub>acq: errors.append("PUBLICATION_AFTER_ACQUISITION")
    if pub and eff and pub<eff: errors.append("PUBLICATION_BEFORE_EFFECTIVE")
    if cutoff:
        for label,dt in (("ACQUISITION",acq),("EFFECTIVE",eff),("PUBLICATION",pub)):
            if dt and dt>cutoff: errors.append(f"FUTURE_DATED_{label}")
        if eff and cutoff-eff>timedelta(days=max_staleness_days): errors.append("STALE_DATA")
    seen=set()
    for i,row in enumerate(rows,1):
        if not isinstance(row,dict): errors.append(f"ROW_{i}_NOT_OBJECT"); continue
        for f in required_fields:
            if row.get(f) in (None,""): errors.append(f"ROW_{i}_MISSING_{f.upper()}")
        key=row.get("id") or tuple(sorted(row.items()))
        if canonical_hash(key) in seen: errors.append("DUPLICATE_OBSERVATION")
        seen.add(canonical_hash(key))
        ident=row.get("security_id") or row.get("ticker") or row.get("id")
        if ident is not None and not ID_RE.match(str(ident)): errors.append("MALFORMED_IDENTIFIER")
    return validation_result(errors,warnings,{"provider":getattr(result,"provider_id",None),"rows":len(rows)})

def validate_config(config: dict[str,Any], allowed_keys: set[str]) -> ValidationResult:
    errors=[]
    if set(config)-allowed_keys: errors.append("UNKNOWN_CONFIG_SETTING")
    if not config.get("schema_version") or not config.get("config_version"): errors.append("MISSING_CONFIG_VERSION")
    return validation_result(errors,[],config)
