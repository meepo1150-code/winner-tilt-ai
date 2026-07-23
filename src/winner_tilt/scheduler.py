"""Dependency-injected production orchestration for Winner Tilt AI."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
import hashlib
import json
import uuid

STAGE_ORDER = (
    "acquire_data",
    "validate_data",
    "create_snapshots",
    "universe_engine",
    "scoring_engine",
    "portfolio_engine",
    "research_engine",
    "decision_journal",
    "dashboard_publish",
)
REQUIRED_STAGES = frozenset(STAGE_ORDER)
OPTIONAL_STAGES = frozenset[str]()
ADAPTER_REQUIRED_STAGES = frozenset(("universe_engine", "scoring_engine", "portfolio_engine", "research_engine", "decision_journal", "dashboard_publish"))


def nowz() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_fingerprint(seed: Any) -> str:
    return hashlib.sha256(json.dumps(seed, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class StageResult:
    name: str
    status: str
    started_at: str
    ended_at: str
    output: Any = None
    error: str | None = None


@dataclass(frozen=True)
class SchedulerRun:
    execution_id: str
    execution_fingerprint: str
    status: str
    started_at: str
    ended_at: str
    stages: tuple[StageResult, ...]
    non_interference: dict[str, bool]


class ProductionScheduler:
    def __init__(
        self,
        *,
        providers=(),
        validator=None,
        snapshot_manager=None,
        adapters: dict[str, Callable[[Any], Any]] | None = None,
        clock=nowz,
        execution_id_factory: Callable[[], str] | None = None,
    ):
        self.providers = tuple(providers)
        self.validator = validator
        self.snapshot_manager = snapshot_manager
        self.adapters = adapters or {}
        self.clock = clock
        self.execution_id_factory = execution_id_factory or (lambda: str(uuid.uuid4()))

    def _fingerprint_seed(self, cutoff_timestamp: str) -> dict[str, Any]:
        return {
            "cutoff": cutoff_timestamp,
            "providers": [provider.metadata().__dict__ for provider in self.providers],
            "adapter_stages": sorted(self.adapters),
            "required_stages": list(STAGE_ORDER),
        }

    def run(self, cutoff_timestamp: str, *, execution_id: str | None = None, run_seed: str | None = None) -> SchedulerRun:
        started = self.clock()
        run_execution_id = execution_id or run_seed or self.execution_id_factory()
        fingerprint = stable_fingerprint(self._fingerprint_seed(cutoff_timestamp))
        context: dict[str, Any] = {"cutoff": cutoff_timestamp, "execution_id": run_execution_id, "execution_fingerprint": fingerprint}
        results: list[StageResult] = []

        for stage_name in STAGE_ORDER:
            stage_started = self.clock()
            try:
                if stage_name == "acquire_data":
                    context["provider_results"] = [provider.fetch(cutoff_timestamp=cutoff_timestamp) for provider in self.providers]
                    output = {"datasets": [result.dataset_type for result in context["provider_results"]]}
                elif stage_name == "validate_data":
                    validations = []
                    for provider, result in zip(self.providers, context.get("provider_results", [])):
                        validations.append(self.validator(result) if self.validator else provider.validate(result))
                    context["validations"] = validations
                    if any(getattr(validation, "status", None) == "FAIL_CLOSED" for validation in validations):
                        raise RuntimeError("VALIDATION_FAILED")
                    output = {"statuses": [validation.status for validation in validations]}
                elif stage_name == "create_snapshots":
                    if self.snapshot_manager is None:
                        raise RuntimeError("SNAPSHOT_MANAGER_REQUIRED")
                    records = []
                    for result in context.get("provider_results", []):
                        source_reference = result.provenance.get("source_reference") if isinstance(result.provenance, dict) else None
                        records.append(
                            self.snapshot_manager.create_snapshot(
                                result.dataset_type,
                                [dict(row) for row in result.rows],
                                acquisition_timestamp=result.acquisition_timestamp,
                                publication_timestamp=result.publication_timestamp,
                                effective_timestamp=result.effective_timestamp,
                                cutoff_timestamp=cutoff_timestamp,
                                source_references=[source_reference],
                            )
                        )
                    context["snapshots"] = records
                    output = {"snapshot_ids": [record.snapshot_id for record in records]}
                else:
                    adapter = self.adapters.get(stage_name)
                    if adapter is None and stage_name in ADAPTER_REQUIRED_STAGES:
                        raise RuntimeError(f"MISSING_REQUIRED_ADAPTER:{stage_name}")
                    output = adapter(context) if adapter else {"optional_stage_skipped": stage_name}
                results.append(StageResult(stage_name, "PASS", stage_started, self.clock(), output, None))
            except Exception as exc:
                results.append(StageResult(stage_name, "FAIL", stage_started, self.clock(), None, f"{type(exc).__name__}:{exc}"))
                break

        status = "PASS" if len(results) == len(STAGE_ORDER) and all(result.status == "PASS" for result in results) else "FAIL_CLOSED"
        return SchedulerRun(
            run_execution_id,
            fingerprint,
            status,
            started,
            self.clock(),
            tuple(results),
            {"universe_modified": False, "scoring_modified": False, "portfolio_modified": False, "backtest_modified": False, "research_modified": False},
        )
