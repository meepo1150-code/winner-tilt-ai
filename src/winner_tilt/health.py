"""Operational health checks for production readiness."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HealthReport:
    state: str
    checks: dict[str, str]
    blockers: tuple[str, ...]
    production_ready: bool


def calculate_health(
    *,
    provider_configs_ok: bool,
    provider_contract_available: bool | None = None,
    synthetic_provider_available: bool | None = None,
    live_provider_available: bool | None = None,
    provider_available: bool | None = None,
    snapshot_fresh: bool,
    validation_failures: int,
    required_dataset_coverage: bool,
    dashboard_inputs_available: bool,
    decision_journal_integrity: bool,
    live_integrations_present: bool = False,
    credentials_present: bool = False,
    licensed_datasets_present: bool = False,
    investment_evidence_present: bool = False,
) -> HealthReport:
    contract_ok = provider_contract_available if provider_contract_available is not None else bool(provider_available)
    synthetic_ok = synthetic_provider_available if synthetic_provider_available is not None else bool(provider_available)
    live_ok = live_provider_available if live_provider_available is not None else live_integrations_present
    checks = {
        "provider_configuration": "healthy" if provider_configs_ok else "failed",
        "provider_contract_availability": "healthy" if contract_ok else "failed",
        "synthetic_offline_provider_availability": "healthy" if synthetic_ok else "failed",
        "live_provider_availability": "healthy" if live_ok else "degraded",
        "snapshot_freshness": "healthy" if snapshot_fresh else "degraded",
        "validation": "healthy" if validation_failures == 0 else "failed",
        "dataset_coverage": "healthy" if required_dataset_coverage else "failed",
        "dashboard_inputs": "healthy" if dashboard_inputs_available else "degraded",
        "decision_journal_integrity": "healthy" if decision_journal_integrity else "failed",
    }
    blockers = []
    for present, blocker in (
        (live_integrations_present, "live vendor integrations absent"),
        (credentials_present, "production credentials absent"),
        (licensed_datasets_present, "licensed datasets absent"),
        (investment_evidence_present, "real investment evidence absent"),
    ):
        if not present:
            blockers.append(blocker)
    state = "failed" if any(value == "failed" for value in checks.values()) else ("degraded" if blockers or any(value == "degraded" for value in checks.values()) else "healthy")
    production_ready = state == "healthy" and not blockers and live_ok
    return HealthReport(state, checks, tuple(blockers), production_ready)
