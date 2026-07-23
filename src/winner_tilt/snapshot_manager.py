"""Immutable deterministic snapshot manager."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import hashlib
import json

SNAPSHOT_SCHEMA_VERSION = "1.0.0"


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def _parse_utc(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SnapshotIntegrityError(f"MISSING_{field.upper()}")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotIntegrityError(f"INVALID_{field.upper()}") from exc
    if dt.tzinfo is None:
        raise SnapshotIntegrityError(f"TIMEZONE_REQUIRED_{field.upper()}")
    dt = dt.astimezone(timezone.utc)
    if dt.utcoffset().total_seconds() != 0:
        raise SnapshotIntegrityError(f"NON_UTC_{field.upper()}")
    return dt


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    dataset_type: str
    content_sha256: str
    metadata_sha256: str
    acquisition_timestamp: str
    publication_timestamp: str | None
    effective_timestamp: str
    cutoff_timestamp: str
    source_references: tuple[str, ...]
    schema_version: str = SNAPSHOT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "dataset_type": self.dataset_type,
            "content_sha256": self.content_sha256,
            "metadata_sha256": self.metadata_sha256,
            "acquisition_timestamp": self.acquisition_timestamp,
            "publication_timestamp": self.publication_timestamp,
            "effective_timestamp": self.effective_timestamp,
            "cutoff_timestamp": self.cutoff_timestamp,
            "source_references": list(self.source_references),
            "schema_version": self.schema_version,
        }


class SnapshotIntegrityError(ValueError):
    pass


class SnapshotManager:
    def __init__(self):
        self._manifest: dict[str, SnapshotRecord] = {}
        self._content: dict[str, str] = {}

    @property
    def manifest(self) -> dict[str, SnapshotRecord]:
        return dict(self._manifest)

    def _validate_timestamps(self, *, acquisition_timestamp: str, publication_timestamp: str | None, effective_timestamp: str, cutoff_timestamp: str) -> None:
        acquisition = _parse_utc(acquisition_timestamp, "acquisition_timestamp")
        effective = _parse_utc(effective_timestamp, "effective_timestamp")
        cutoff = _parse_utc(cutoff_timestamp, "cutoff_timestamp")
        publication = _parse_utc(publication_timestamp, "publication_timestamp") if publication_timestamp else None
        if effective > acquisition:
            raise SnapshotIntegrityError("EFFECTIVE_AFTER_ACQUISITION")
        if publication and publication > acquisition:
            raise SnapshotIntegrityError("PUBLICATION_AFTER_ACQUISITION")
        if publication and publication < effective:
            raise SnapshotIntegrityError("PUBLICATION_BEFORE_EFFECTIVE")
        if acquisition > cutoff:
            raise SnapshotIntegrityError("ACQUISITION_AFTER_CUTOFF")
        if effective > cutoff:
            raise SnapshotIntegrityError("EFFECTIVE_AFTER_CUTOFF")
        if publication and publication > cutoff:
            raise SnapshotIntegrityError("PUBLICATION_AFTER_CUTOFF")

    def expected_snapshot_id(self, *, dataset_type: str, content_sha256: str, effective_timestamp: str, cutoff_timestamp: str, source_references: tuple[str, ...]) -> str:
        return sha256(
            {
                "dataset_type": dataset_type,
                "content_sha256": content_sha256,
                "effective_timestamp": effective_timestamp,
                "cutoff_timestamp": cutoff_timestamp,
                "source_references": list(source_references),
                "schema_version": SNAPSHOT_SCHEMA_VERSION,
            }
        )[:32]

    def expected_metadata_sha256(self, record: SnapshotRecord) -> str:
        metadata = record.to_dict() | {"metadata_sha256": ""}
        return sha256(metadata)

    def create_snapshot(
        self,
        dataset_type: str,
        payload: Any,
        *,
        acquisition_timestamp: str,
        publication_timestamp: str | None,
        effective_timestamp: str,
        cutoff_timestamp: str,
        source_references: list[str],
    ) -> SnapshotRecord:
        refs = tuple(source_references or ())
        if not refs or any(not isinstance(ref, str) or not ref.strip() for ref in refs):
            raise SnapshotIntegrityError("SOURCE_REFERENCES_REQUIRED")
        self._validate_timestamps(
            acquisition_timestamp=acquisition_timestamp,
            publication_timestamp=publication_timestamp,
            effective_timestamp=effective_timestamp,
            cutoff_timestamp=cutoff_timestamp,
        )
        content = canonical_json(payload)
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        snapshot_id = self.expected_snapshot_id(
            dataset_type=dataset_type,
            content_sha256=content_hash,
            effective_timestamp=effective_timestamp,
            cutoff_timestamp=cutoff_timestamp,
            source_references=refs,
        )
        if snapshot_id in self._manifest:
            if self._content[snapshot_id] != content:
                raise SnapshotIntegrityError("SNAPSHOT_ID_COLLISION")
            return self._manifest[snapshot_id]
        record = SnapshotRecord(snapshot_id, dataset_type, content_hash, "", acquisition_timestamp, publication_timestamp, effective_timestamp, cutoff_timestamp, refs)
        record = SnapshotRecord(**(record.to_dict() | {"metadata_sha256": self.expected_metadata_sha256(record)}))
        self._manifest[snapshot_id] = record
        self._content[snapshot_id] = content
        return record

    def verify_integrity(self, record: SnapshotRecord, payload: Any) -> bool:
        if record.snapshot_id not in self._manifest:
            raise SnapshotIntegrityError("UNKNOWN_SNAPSHOT")
        if self._manifest[record.snapshot_id] != record:
            raise SnapshotIntegrityError("MUTATED_MANIFEST_RECORD")
        if hashlib.sha256(canonical_json(payload).encode()).hexdigest() != record.content_sha256:
            raise SnapshotIntegrityError("CONTENT_HASH_MISMATCH")
        if self.expected_metadata_sha256(record) != record.metadata_sha256:
            raise SnapshotIntegrityError("METADATA_HASH_MISMATCH")
        if self.expected_snapshot_id(dataset_type=record.dataset_type, content_sha256=record.content_sha256, effective_timestamp=record.effective_timestamp, cutoff_timestamp=record.cutoff_timestamp, source_references=record.source_references) != record.snapshot_id:
            raise SnapshotIntegrityError("SNAPSHOT_ID_MISMATCH")
        self._validate_timestamps(
            acquisition_timestamp=record.acquisition_timestamp,
            publication_timestamp=record.publication_timestamp,
            effective_timestamp=record.effective_timestamp,
            cutoff_timestamp=record.cutoff_timestamp,
        )
        return True

    def decision_journal_source_reference(self, record: SnapshotRecord) -> dict[str, Any]:
        return {"snapshot_id": record.snapshot_id, "content_sha256": record.content_sha256, "source_references": list(record.source_references), "schema_version": record.schema_version}
