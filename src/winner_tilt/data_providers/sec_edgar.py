"""Controlled SEC EDGAR Company Facts fundamentals pilot.

The adapter is offline-by-default and transport-injected. It normalizes a
small allowlisted Company Facts payload into the existing ProviderResult
contract without connecting the data to downstream investment engines.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable, Mapping

from .base import ProviderMetadata, ProviderResult

SEC_EDGAR_PROVIDER_ID = "sec-edgar-companyfacts"
SEC_EDGAR_VENDOR = "U.S. Securities and Exchange Commission"
SEC_EDGAR_BASE_URL = "https://data.sec.gov/api/xbrl/companyfacts"
SUPPORTED_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A"})


class SecEdgarPolicyError(ValueError):
    """Raised when pilot policy or payload requirements are not satisfied."""


@dataclass(frozen=True)
class SecEdgarPilotConfig:
    allowed_ciks: tuple[str, ...]
    user_agent: str | None = None
    live_enabled: bool = False
    max_requests_per_second: float = 2.0
    retain_raw_payload: bool = False

    def validate(self) -> None:
        normalized = tuple(_normalize_cik(cik) for cik in self.allowed_ciks)
        if not normalized:
            raise SecEdgarPolicyError("SEC_EDGAR_ALLOWLIST_REQUIRED")
        if len(set(normalized)) != len(normalized):
            raise SecEdgarPolicyError("SEC_EDGAR_DUPLICATE_ALLOWLIST_CIK")
        if not (0 < self.max_requests_per_second <= 2.0):
            raise SecEdgarPolicyError("SEC_EDGAR_RATE_LIMIT_EXCEEDS_PILOT_POLICY")
        if self.retain_raw_payload:
            raise SecEdgarPolicyError("SEC_EDGAR_RAW_RETENTION_NOT_APPROVED")
        if self.live_enabled and not (self.user_agent or "").strip():
            raise SecEdgarPolicyError("SEC_EDGAR_USER_AGENT_REQUIRED")


def _normalize_cik(value: str | int) -> str:
    text = str(value).strip()
    if not text.isdigit() or len(text) > 10:
        raise SecEdgarPolicyError("SEC_EDGAR_INVALID_CIK")
    return text.zfill(10)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_now_iso(clock: Callable[[], datetime]) -> str:
    value = clock()
    if value.tzinfo is None:
        raise SecEdgarPolicyError("SEC_EDGAR_CLOCK_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _accepted_timestamp(fact: Mapping[str, Any]) -> str:
    accepted = fact.get("accepted")
    if not isinstance(accepted, str) or not accepted.strip():
        raise SecEdgarPolicyError("SEC_EDGAR_ACCEPTED_TIMESTAMP_REQUIRED")
    try:
        parsed = datetime.fromisoformat(accepted.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SecEdgarPolicyError("SEC_EDGAR_INVALID_ACCEPTED_TIMESTAMP") from exc
    if parsed.tzinfo is None:
        raise SecEdgarPolicyError("SEC_EDGAR_ACCEPTED_TIMESTAMP_TIMEZONE_REQUIRED")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_companyfacts(payload: Mapping[str, Any], *, expected_cik: str | int) -> tuple[dict[str, Any], ...]:
    """Normalize an SEC Company Facts response deterministically.

    Unknown fields are ignored. Amended filings remain distinct through the
    accession number and form. No unit conversion or silent deduplication occurs.
    """
    cik = _normalize_cik(expected_cik)
    payload_cik = _normalize_cik(payload.get("cik", ""))
    if payload_cik != cik:
        raise SecEdgarPolicyError("SEC_EDGAR_CIK_MISMATCH")

    facts = payload.get("facts")
    if not isinstance(facts, Mapping) or not facts:
        raise SecEdgarPolicyError("SEC_EDGAR_FACTS_REQUIRED")

    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for taxonomy in sorted(facts):
        concepts = facts[taxonomy]
        if not isinstance(concepts, Mapping):
            continue
        for concept in sorted(concepts):
            definition = concepts[concept]
            if not isinstance(definition, Mapping):
                continue
            units = definition.get("units")
            if not isinstance(units, Mapping):
                continue
            for unit in sorted(units):
                entries = units[unit]
                if not isinstance(entries, list):
                    continue
                for fact in entries:
                    if not isinstance(fact, Mapping):
                        continue
                    form = fact.get("form")
                    if form not in SUPPORTED_FORMS:
                        continue
                    accession = fact.get("accn")
                    report_end = fact.get("end")
                    filed = fact.get("filed")
                    value = fact.get("val")
                    if not all(isinstance(v, str) and v for v in (accession, report_end, filed)):
                        raise SecEdgarPolicyError("SEC_EDGAR_REQUIRED_FACT_METADATA_MISSING")
                    accepted = _accepted_timestamp(fact)
                    natural_key = (cik, taxonomy, concept, unit, report_end, accession)
                    if natural_key in seen:
                        raise SecEdgarPolicyError("SEC_EDGAR_DUPLICATE_NATURAL_KEY")
                    seen.add(natural_key)
                    rows.append({
                        "id": f"{cik}:{taxonomy}:{concept}:{unit}:{report_end}:{accession}",
                        "security_id": cik,
                        "cik": cik,
                        "taxonomy": taxonomy,
                        "concept": concept,
                        "unit": unit,
                        "value": value,
                        "report_end": report_end,
                        "filed_date": filed,
                        "accepted_timestamp": accepted,
                        "form": form,
                        "accession_number": accession,
                        "fiscal_year": fact.get("fy"),
                        "fiscal_period": fact.get("fp"),
                        "frame": fact.get("frame"),
                        "is_amendment": form.endswith("/A"),
                    })
    if not rows:
        raise SecEdgarPolicyError("SEC_EDGAR_NO_SUPPORTED_FACTS")
    return tuple(sorted(rows, key=lambda row: row["id"]))


class SecEdgarCompanyFactsProvider:
    """Isolated ingest-only provider with dependency-injected transport."""

    def __init__(
        self,
        config: SecEdgarPilotConfig,
        *,
        transport: Callable[[str, Mapping[str, str]], Mapping[str, Any]] | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        config.validate()
        self._config = config
        self._transport = transport
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._latest: str | None = None

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            SEC_EDGAR_PROVIDER_ID,
            SEC_EDGAR_VENDOR,
            "fundamentals",
            live_integration=True,
            credentials_required=False,
        )

    def fetch(self, *, cik: str | int, payload: Mapping[str, Any] | None = None) -> ProviderResult:
        normalized_cik = _normalize_cik(cik)
        if normalized_cik not in {_normalize_cik(item) for item in self._config.allowed_ciks}:
            raise SecEdgarPolicyError("SEC_EDGAR_CIK_NOT_ALLOWLISTED")

        source_url = f"{SEC_EDGAR_BASE_URL}/CIK{normalized_cik}.json"
        if payload is None:
            if not self._config.live_enabled:
                raise SecEdgarPolicyError("SEC_EDGAR_LIVE_MODE_DISABLED")
            if self._transport is None:
                raise SecEdgarPolicyError("SEC_EDGAR_TRANSPORT_REQUIRED")
            payload = self._transport(source_url, {"User-Agent": self._config.user_agent or ""})

        if not isinstance(payload, Mapping):
            raise SecEdgarPolicyError("SEC_EDGAR_RESPONSE_NOT_OBJECT")
        acquired_at = _utc_now_iso(self._clock)
        rows = normalize_companyfacts(payload, expected_cik=normalized_cik)
        publication_timestamp = max(row["accepted_timestamp"] for row in rows)
        effective_timestamp = max(f"{row['report_end']}T00:00:00Z" for row in rows)
        if publication_timestamp > acquired_at:
            raise SecEdgarPolicyError("SEC_EDGAR_FUTURE_ACCEPTANCE_TIMESTAMP")
        self._latest = publication_timestamp
        return ProviderResult(
            dataset_type="fundamentals",
            rows=rows,
            provider_id=SEC_EDGAR_PROVIDER_ID,
            vendor=SEC_EDGAR_VENDOR,
            acquisition_timestamp=acquired_at,
            effective_timestamp=effective_timestamp,
            schema_version="1.0.0",
            provenance={
                "source_reference": source_url,
                "retrieval_method": "fixture" if not self._config.live_enabled or self._transport is None else "https",
                "license": "SEC public filing data; usage subject to SEC fair-access policy",
                "raw_content_sha256": _canonical_hash(payload),
                "raw_payload_retained": False,
                "pilot_scope": "ingest_only_no_downstream_consumption",
            },
            validation_state="unvalidated",
            publication_timestamp=publication_timestamp,
        )

    def validate(self, result: ProviderResult):
        from winner_tilt.validation import validate_provider_result

        return validate_provider_result(
            result,
            natural_key_fields=("cik", "taxonomy", "concept", "unit", "report_end", "accession_number"),
            required_fields=("accepted_timestamp", "form", "accession_number", "unit", "report_end"),
        )

    def latest_timestamp(self) -> str | None:
        return self._latest
