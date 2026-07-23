#!/usr/bin/env python3
"""Winner Tilt AI production-architecture walk-forward backtest engine v2.0.

The engine is deterministic and point-in-time aware. A run is labelled
PRODUCTION_VALID only when the supplied data manifest passes every required
integrity gate; otherwise it is VALIDATION_ONLY.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

TRADING_DAYS = 252


def read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_hash(obj: Any) -> str:
    raw=json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def parse_date(raw: str) -> date:
    return date.fromisoformat(raw[:10])


def load_long_csv(path: str) -> list[dict[str,str]]:
    with open(path,newline="",encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def previous_or_equal(sorted_dates: list[date], target: date) -> date | None:
    lo,hi=0,len(sorted_dates)-1; ans=None
    while lo<=hi:
        mid=(lo+hi)//2
        if sorted_dates[mid] <= target: ans=sorted_dates[mid]; lo=mid+1
        else: hi=mid-1
    return ans


def next_or_equal(sorted_dates: list[date], target: date) -> date | None:
    lo,hi=0,len(sorted_dates)-1; ans=None
    while lo<=hi:
        mid=(lo+hi)//2
        if sorted_dates[mid] >= target: ans=sorted_dates[mid]; hi=mid-1
        else: lo=mid+1
    return ans


def performance(values: list[float], risk_free_rate: float=0.0) -> dict[str,Any]:
    if len(values)<2:
        return {k:None for k in ("total_return","cagr","annualized_return","annualized_volatility","sharpe","sortino","max_drawdown")}
    rets=[values[i]/values[i-1]-1 for i in range(1,len(values))]
    years=max((len(values)-1)/TRADING_DAYS,1/TRADING_DAYS)
    total=values[-1]/values[0]-1
    cagr=(values[-1]/values[0])**(1/years)-1
    mean=sum(rets)/len(rets)
    var=sum((x-mean)**2 for x in rets)/max(1,len(rets)-1)
    vol=math.sqrt(var)*math.sqrt(TRADING_DAYS)
    downside=[min(0,x) for x in rets]
    dvol=math.sqrt(sum(x*x for x in downside)/max(1,len(downside)))*math.sqrt(TRADING_DAYS)
    peak=values[0]; mdd=0.0
    for v in values:
        peak=max(peak,v); mdd=min(mdd,v/peak-1)
    ann=mean*TRADING_DAYS
    excess=ann-risk_free_rate
    return {"total_return":total,"cagr":cagr,"annualized_return":ann,"annualized_volatility":vol,
            "sharpe":excess/vol if vol else None,"sortino":excess/dvol if dvol else None,"max_drawdown":mdd}


def validate_manifest(manifest: dict[str,Any], cfg: dict[str,Any]) -> dict[str,Any]:
    required=cfg["integrity_gates"]
    checks={}
    for key in required:
        checks[key]=bool(manifest.get(key,False))
    passed=all(checks.values())
    return {"checks":checks,"passed":passed,"failed":[k for k,v in checks.items() if not v]}


def load_prices(path: str) -> tuple[list[date],dict[date,dict[str,float]]]:
    rows=load_long_csv(path); by=defaultdict(dict)
    for r in rows:
        px=float(r["adjusted_close"])
        if px<=0: raise ValueError("adjusted_close must be positive")
        by[parse_date(r["date"])][r["security_id"]]=px
    dates=sorted(by)
    if not dates: raise ValueError("price file is empty")
    return dates,dict(by)


def load_benchmark(path: str) -> dict[date,float]:
    rows=load_long_csv(path); out={}
    for r in rows: out[parse_date(r["date"])]=float(r["adjusted_close"])
    return out


def load_score_vintages(path: str) -> dict[date,list[dict[str,Any]]]:
    raw=read_json(path); out={}
    for v in raw["vintages"]:
        cutoff=parse_date(v["information_cutoff"])
        generated=parse_date(v.get("generated_at",v["information_cutoff"]))
        if generated < cutoff: raise ValueError("generated_at cannot precede information_cutoff")
        for row in v["results"]:
            available=parse_date(row.get("available_at",v["information_cutoff"]))
            if available > cutoff:
                raise ValueError(f"LOOKAHEAD: {row['security_id']} available_at exceeds cutoff")
        out[cutoff]=v["results"]
    return dict(sorted(out.items()))


def load_memberships(path: str) -> dict[str,list[tuple[date,date|None,str]]]:
    out=defaultdict(list)
    for r in load_long_csv(path):
        out[r["security_id"]].append((parse_date(r["valid_from"]),parse_date(r["valid_to"]) if r.get("valid_to") else None,r.get("status","ACTIVE")))
    return out


def active_on(memberships, sid: str, d: date) -> bool:
    return any(start<=d and (end is None or d<=end) and status=="ACTIVE" for start,end,status in memberships.get(sid,[]))


def select_equal_weight(results: list[dict[str,Any]], memberships, cutoff: date, count: int) -> dict[str,float]:
    eligible=[r for r in results if r.get("eligible",True) and r.get("total_score") is not None and active_on(memberships,r["security_id"],cutoff)]
    eligible.sort(key=lambda r:(int(r.get("overall_rank",10**9)),-float(r["total_score"]),r["security_id"]))
    chosen=eligible[:count]
    if len(chosen)<count: raise ValueError(f"Only {len(chosen)} eligible securities at {cutoff}; need {count}")
    return {r["security_id"]:1.0/count for r in chosen}


def execution_cost(notional: float, cfg: dict[str,Any]) -> float:
    bps=cfg["costs"]["commission_bps"]+cfg["costs"]["spread_bps"]+cfg["costs"]["slippage_bps"]
    return abs(notional)*bps/10000.0


def run_backtest(cfg, prices_dates, prices, benchmark, vintages, memberships, manifest):
    start=parse_date(cfg["period"]["start"]); end=parse_date(cfg["period"]["end"])
    dates=[d for d in prices_dates if start<=d<=end]
    if not dates: raise ValueError("No price dates in configured period")
    score_dates=sorted(vintages)
    rebal_months=set(cfg["rebalance"]["months"])
    initial=float(cfg["capital"]["initial"]); cash=initial; shares=defaultdict(float)
    target_weights={}; ledger=[]; rebalance_records=[]; curve=[]; integrity_flags=[]
    last_rebalance_period=None
    benchmark_base=None

    for d in dates:
        period=(d.year,d.month)
        should_rebalance=d.month in rebal_months and period!=last_rebalance_period
        if should_rebalance:
            cutoff=previous_or_equal(score_dates,d)
            if cutoff is None: integrity_flags.append(f"NO_SCORE_VINTAGE:{d}")
            else:
                targets=select_equal_weight(vintages[cutoff],memberships,cutoff,cfg["portfolio"]["holdings_count"])
                # Mark portfolio before trading.
                nav=cash+sum(shares[s]*prices[d].get(s,0.0) for s in shares)
                all_ids=sorted(set(shares)|set(targets))
                traded=0.0; costs=0.0
                for sid in all_ids:
                    if sid not in prices[d]:
                        if shares[sid]!=0: integrity_flags.append(f"MISSING_PRICE:{d}:{sid}")
                        continue
                    desired=nav*targets.get(sid,0.0)
                    current=shares[sid]*prices[d][sid]
                    notional=desired-current
                    if abs(notional)<1e-10: continue
                    cost=execution_cost(notional,cfg)
                    qty=notional/prices[d][sid]
                    shares[sid]+=qty; cash-=notional+cost
                    traded+=abs(notional); costs+=cost
                    ledger.append({"date":d.isoformat(),"security_id":sid,"side":"BUY" if notional>0 else "SELL","quantity":qty,"price":prices[d][sid],"notional":notional,"cost":cost,"score_cutoff":cutoff.isoformat()})
                target_weights=targets; last_rebalance_period=period
                rebalance_records.append({"date":d.isoformat(),"score_cutoff":cutoff.isoformat(),"turnover":traded/(2*nav) if nav else 0.0,"cost":costs,"holdings":sorted(targets)})
        value=cash+sum(qty*prices[d].get(sid,0.0) for sid,qty in shares.items())
        b=benchmark.get(d)
        if b is not None and benchmark_base is None: benchmark_base=b
        bval=initial*(b/benchmark_base) if b is not None and benchmark_base else None
        curve.append({"date":d.isoformat(),"portfolio_value":value,"benchmark_value":bval,"cash":cash})

    pvals=[r["portfolio_value"] for r in curve]
    bvals=[r["benchmark_value"] for r in curve if r["benchmark_value"] is not None]
    pm=performance(pvals,cfg.get("risk_free_rate",0.0)); bm=performance(bvals,cfg.get("risk_free_rate",0.0)) if len(bvals)==len(curve) else {}
    total_turnover=sum(r["turnover"] for r in rebalance_records)
    total_cost=sum(r["cost"] for r in rebalance_records)
    rel={}
    if pm.get("cagr") is not None and bm.get("cagr") is not None:
        rel={"cagr_spread":pm["cagr"]-bm["cagr"],"ending_value_spread":pvals[-1]-bvals[-1]}
    validation=validate_manifest(manifest,cfg)
    status="PRODUCTION_VALID" if validation["passed"] and not integrity_flags else "VALIDATION_ONLY"
    return {"engine_version":"2.0.0","validation_status":status,"configuration_sha256":canonical_hash(cfg),
            "data_manifest_sha256":canonical_hash(manifest),"integrity_validation":validation,
            "integrity_flags":sorted(set(integrity_flags)),"metrics":pm,"benchmark_metrics":bm,"relative_metrics":rel,
            "turnover":{"cumulative_one_way":total_turnover},"transaction_costs":total_cost,
            "rebalance_records":rebalance_records,"transaction_ledger":ledger,"equity_curve":curve}


def main():
    ap=argparse.ArgumentParser()
    for arg in ("config","prices","benchmark","score-vintages","memberships","data-manifest","output"):
        ap.add_argument("--"+arg,required=True)
    a=ap.parse_args(); cfg=read_json(a.config); manifest=read_json(a.data_manifest)
    dates,prices=load_prices(a.prices); benchmark=load_benchmark(a.benchmark)
    vintages=load_score_vintages(a.score_vintages); memberships=load_memberships(a.memberships)
    out=run_backtest(cfg,dates,prices,benchmark,vintages,memberships,manifest)
    Path(a.output).write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")

if __name__=="__main__": main()
