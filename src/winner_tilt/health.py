"""Operational health checks for production readiness."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
@dataclass(frozen=True)
class HealthReport:
    state:str; checks:dict[str,str]; blockers:tuple[str,...]; production_ready:bool

def calculate_health(*, provider_configs_ok:bool, provider_available:bool, snapshot_fresh:bool, validation_failures:int, required_dataset_coverage:bool, dashboard_inputs_available:bool, decision_journal_integrity:bool, live_integrations_present:bool=False, credentials_present:bool=False, licensed_datasets_present:bool=False, investment_evidence_present:bool=False)->HealthReport:
    checks={"provider_configuration":"healthy" if provider_configs_ok else "failed","provider_availability":"healthy" if provider_available else "failed","snapshot_freshness":"healthy" if snapshot_fresh else "degraded","validation":"healthy" if validation_failures==0 else "failed","dataset_coverage":"healthy" if required_dataset_coverage else "failed","dashboard_inputs":"healthy" if dashboard_inputs_available else "degraded","decision_journal_integrity":"healthy" if decision_journal_integrity else "failed"}
    blockers=[]
    for ok,name in [(live_integrations_present,"live vendor integrations absent"),(credentials_present,"production credentials absent"),(licensed_datasets_present,"licensed datasets absent"),(investment_evidence_present,"real investment evidence absent")]:
        if not ok: blockers.append(name)
    state="failed" if any(v=="failed" for v in checks.values()) else ("degraded" if blockers or any(v=="degraded" for v in checks.values()) else "healthy")
    return HealthReport(state,checks,tuple(blockers),state=="healthy" and not blockers)
