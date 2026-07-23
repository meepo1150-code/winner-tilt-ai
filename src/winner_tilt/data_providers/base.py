"""Deterministic production data provider contracts for Winner Tilt AI."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
import re

PROVIDER_CONTRACT_VERSION = "1.0.0"
UTC = timezone.utc
SECRET_KEY_RE = re.compile(r"(api[_-]?key|token|secret|password|authorization|credential)", re.IGNORECASE)
ENV_PLACEHOLDER_RE = re.compile(r"^\$\{[A-Z][A-Z0-9_]*\}$")


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

    def __init__(
        self,
        metadata: ProviderMetadata,
        rows: list[dict[str, Any]],
        *,
        acquired_at: str,
        effective_at: str,
        published_at: str | None = None,
        provenance: dict[str, Any] | None = None,
        natural_key_fields: tuple[str, ...] = ("id",),
    ):
        self._metadata = metadata
        self._rows = tuple(dict(row) for row in rows)
        self._acquired_at = acquired_at
        self._effective_at = effective_at
        self._published_at = published_at
        self._natural_key_fields = natural_key_fields
        self._provenance = (
            {"source_reference": "synthetic://winner-tilt/offline", "license": "synthetic", "retrieval_method": "in_memory"}
            if provenance is None
            else provenance
        )

    def fetch(self, **kwargs: Any) -> ProviderResult:
        return ProviderResult(
            self._metadata.dataset_type,
            self._rows,
            self._metadata.provider_id,
            self._metadata.vendor,
            self._acquired_at,
            self._effective_at,
            self._metadata.schema_version,
            dict(self._provenance),
            "unvalidated",
            self._published_at,
        )

    def validate(self, result: ProviderResult):
        from winner_tilt.validation import validate_provider_result

        return validate_provider_result(result, natural_key_fields=self._natural_key_fields)

    def metadata(self) -> ProviderMetadata:
        return self._metadata

    def latest_timestamp(self) -> str | None:
        return self._published_at or self._effective_at


def _validate_config_node(value: Any, *, path: tuple[str, ...], allowed_keys_by_path: dict[tuple[str, ...], set[str]]) -> None:
    if isinstance(value, dict):
        allowed = allowed_keys_by_path.get(path)
        if allowed is not None:
            unknown = set(value) - allowed
            if unknown:
                raise ValueError(f"UNKNOWN_PROVIDER_CONFIG_SETTING:{'.'.join(path) or '<root>'}:{','.join(sorted(unknown))}")
        for key, child in value.items():
            if SECRET_KEY_RE.search(str(key)):
                if not isinstance(child, str) or not ENV_PLACEHOLDER_RE.match(child):
                    raise ValueError(f"SECRET_VALUE_NOT_ALLOWED:{'.'.join(path + (str(key),))}")
            _validate_config_node(child, path=path + (str(key),), allowed_keys_by_path=allowed_keys_by_path)
    elif isinstance(value, list):
        for child in value:
            _validate_config_node(child, path=path, allowed_keys_by_path=allowed_keys_by_path)


def validate_provider_config(config: dict[str, Any]) -> bool:
    """Fail closed on unknown settings and literal secret values.

    Secret-like keys may only contain explicit environment-variable placeholders
    such as ``${VENDOR_API_KEY}``; unrelated values containing "env" do not make
    literal secrets acceptable.
    """

    allowed = {
        (): {"schema_version", "config_version", "providers", "environment_placeholders", "live_integrations_enabled"},
        ("providers",): {"dataset_type", "provider_id", "vendor", "enabled", "credential_env_var", "api_key", "token", "secret", "password", "authorization", "credential"},
    }
    if config.get("schema_version") != PROVIDER_CONTRACT_VERSION or config.get("config_version") != PROVIDER_CONTRACT_VERSION:
        raise ValueError("PROVIDER_CONFIG_VERSION_MISMATCH")
    if config.get("live_integrations_enabled") is not False:
        raise ValueError("LIVE_INTEGRATIONS_MUST_BE_FALSE")
    _validate_config_node(config, path=(), allowed_keys_by_path=allowed)
    return True
