"""Deterministic production data provider contracts for Winner Tilt AI."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
import re

PROVIDER_CONTRACT_VERSION = "1.0.0"
UTC = timezone.utc

@dataclass(frozen=True)
class ProviderMetadata:
    provider_id: str
    vendor: str
    dataset_type: str
    schema_version: str = PROVIDER_CONTRACT_VERSION
    contract_version: str = PROVIDER_CONTRACT_VERSION
    live_integration: bool = False
    credentials_required: bool = False

@dataclass(frozen=True)
class ProviderResult:
    dataset_type: str
    rows: tuple[dict[str, Any], ...]
    provider_id: str
    vendor: str
    acquisition_timestamp: str
    effective_timestamp: str
    schema_version: str
    provenance: dict[str, Any]
    validation_state: str = "unvalidated"
    publication_timestamp: str | None = None

class DataProvider(Protocol):
    def fetch(self, **kwargs: Any) -> ProviderResult: ...
    def validate(self, result: ProviderResult) -> Any: ...
    def metadata(self) -> ProviderMetadata: ...
    def latest_timestamp(self) -> str | None: ...

def utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("timezone-aware datetime required")
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")

class InMemoryProvider:
    """Offline deterministic provider used by tests and adapters."""
    def __init__(self, metadata: ProviderMetadata, rows: list[dict[str, Any]], *, acquired_at: str, effective_at: str, published_at: str | None = None, provenance: dict[str, Any] | None = None):
        self._metadata=metadata; self._rows=tuple(dict(r) for r in rows); self._acquired_at=acquired_at; self._effective_at=effective_at; self._published_at=published_at
        self._provenance={"source_reference":"synthetic://winner-tilt/offline", "license":"synthetic", "retrieval_method":"in_memory"} if provenance is None else provenance
    def fetch(self, **kwargs: Any) -> ProviderResult:
        return ProviderResult(self._metadata.dataset_type,self._rows,self._metadata.provider_id,self._metadata.vendor,self._acquired_at,self._effective_at,self._metadata.schema_version,dict(self._provenance),"unvalidated",self._published_at)
    def validate(self, result: ProviderResult):
        from winner_tilt.validation import validate_provider_result
        return validate_provider_result(result)
    def metadata(self) -> ProviderMetadata: return self._metadata
    def latest_timestamp(self) -> str | None: return self._published_at or self._effective_at

def validate_provider_config(config: dict[str, Any]) -> bool:
    allowed={"schema_version","config_version","providers","environment_placeholders","live_integrations_enabled"}
    if set(config)-allowed: raise ValueError("UNKNOWN_PROVIDER_CONFIG_SETTING")
    if config.get("live_integrations_enabled") is not False: raise ValueError("LIVE_INTEGRATIONS_MUST_BE_FALSE")
    text=str(config).lower()
    if any(marker in text for marker in ("api_key", "token", "secret", "password")) and "env" not in text:
        raise ValueError("SECRET_VALUE_NOT_ALLOWED")
    return True
