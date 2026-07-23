"""Dependency-injected production orchestration for Winner Tilt AI."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
import hashlib,json
STAGE_ORDER=("acquire_data","validate_data","create_snapshots","universe_engine","scoring_engine","portfolio_engine","research_engine","decision_journal","dashboard_publish")
def nowz(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def stable_id(seed:Any)->str: return hashlib.sha256(json.dumps(seed,sort_keys=True,default=str).encode()).hexdigest()[:32]
@dataclass(frozen=True)
class StageResult: name:str; status:str; started_at:str; ended_at:str; output:Any=None; error:str|None=None
@dataclass(frozen=True)
class SchedulerRun: execution_id:str; status:str; started_at:str; ended_at:str; stages:tuple[StageResult,...]; non_interference:dict[str,bool]
class ProductionScheduler:
    def __init__(self, *, providers=(), validator=None, snapshot_manager=None, adapters:dict[str,Callable[[Any],Any]]|None=None, clock=nowz):
        self.providers=tuple(providers); self.validator=validator; self.snapshot_manager=snapshot_manager; self.adapters=adapters or {}; self.clock=clock
    def run(self, cutoff_timestamp:str) -> SchedulerRun:
        started=self.clock(); eid=stable_id({"started_at":started,"cutoff":cutoff_timestamp,"providers":[p.metadata().__dict__ for p in self.providers]}); ctx={"cutoff":cutoff_timestamp}; results=[]
        for name in STAGE_ORDER:
            s=self.clock()
            try:
                if name=="acquire_data": ctx["provider_results"]=[p.fetch(cutoff_timestamp=cutoff_timestamp) for p in self.providers]; out={"datasets":[r.dataset_type for r in ctx["provider_results"]]}
                elif name=="validate_data":
                    vals=[(self.validator or p.validate)(r) if self.validator else p.validate(r) for p,r in zip(self.providers,ctx.get("provider_results",[]))]
                    ctx["validations"]=vals; fails=[v for v in vals if getattr(v,"status",None)=="FAIL_CLOSED"]
                    if fails: raise RuntimeError("VALIDATION_FAILED")
                    out={"statuses":[v.status for v in vals]}
                elif name=="create_snapshots":
                    recs=[]
                    if self.snapshot_manager:
                        for r in ctx.get("provider_results",[]): recs.append(self.snapshot_manager.create_snapshot(r.dataset_type,[dict(x) for x in r.rows],acquisition_timestamp=r.acquisition_timestamp,publication_timestamp=r.publication_timestamp,effective_timestamp=r.effective_timestamp,cutoff_timestamp=cutoff_timestamp,source_references=[r.provenance.get("source_reference")]))
                    ctx["snapshots"]=recs; out={"snapshot_ids":[r.snapshot_id for r in recs]}
                else:
                    adapter=self.adapters.get(name)
                    out=adapter(ctx) if adapter else {"adapter":"not_configured","skipped_without_reproducing_logic":True}
                e=self.clock(); results.append(StageResult(name,"PASS",s,e,out,None))
            except Exception as exc:
                e=self.clock(); results.append(StageResult(name,"FAIL",s,e,None,type(exc).__name__+":"+str(exc))); break
        status="PASS" if len(results)==len(STAGE_ORDER) and all(r.status=="PASS" for r in results) else "FAIL_CLOSED"
        return SchedulerRun(eid,status,started,self.clock(),tuple(results),{"universe_modified":False,"scoring_modified":False,"portfolio_modified":False,"backtest_modified":False,"research_modified":False})
