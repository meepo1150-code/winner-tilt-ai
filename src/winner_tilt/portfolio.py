#!/usr/bin/env python3
"""Winner Tilt AI deterministic Portfolio Engine v1.0.

Converts a frozen monthly score run into 15 holdings + 15 reserves while
respecting configurable concentration, rebalance-buffer, turnover and sizing
rules. The engine never changes stock scores.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_hash(obj: Any) -> str:
    raw=json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def load_universe(path: str) -> dict[str, dict[str,str]]:
    with open(path,newline="",encoding="utf-8-sig") as f:
        return {r["WT_ID"]:r for r in csv.DictReader(f)}


def exposure_tokens(raw: str) -> list[str]:
    # v1 uses the frozen universe phrase as one auditable exposure bucket.
    return [raw.strip()] if raw and raw.strip() else ["UNCLASSIFIED"]


def candidate_rows(score_run: dict[str,Any], universe: dict[str,dict[str,str]]) -> list[dict[str,Any]]:
    rows=[]
    for s in score_run["results"]:
        if not s.get("eligible") or s.get("total_score") is None or s["security_id"] not in universe:
            continue
        u=universe[s["security_id"]]
        rows.append({
            "security_id":s["security_id"],"ticker":s["ticker"],"score":float(s["total_score"]),
            "overall_rank":int(s["overall_rank"]),"pool":u["Pool"],"business_stage":u["Business_Stage"],
            "universe_group":u["Universe_Group"],"primary_theme":u["Primary_Theme"],
            "economic_exposure":u["Economic_Exposure"],"quality_tier":u["Quality_Tier"],
            "category_scores":s.get("category_scores",{}),"score_flags":s.get("flags",[]),
        })
    return sorted(rows,key=lambda r:(r["overall_rank"],r["security_id"]))


def allowed(row:dict[str,Any], selected:list[dict[str,Any]], cfg:dict[str,Any], target:int) -> tuple[bool,str|None]:
    c=cfg["concentration"]
    pool=Counter(x["pool"] for x in selected); groups=Counter(x["universe_group"] for x in selected)
    themes=Counter(x["primary_theme"] for x in selected); stages=Counter(x["business_stage"] for x in selected)
    exposures=Counter(e for x in selected for e in exposure_tokens(x["economic_exposure"]))
    if row["pool"]=="Emerging" and pool["Emerging"]>=c["max_emerging_positions"]: return False,"MAX_EMERGING"
    if groups[row["universe_group"]]>=c["max_per_universe_group"]: return False,"MAX_UNIVERSE_GROUP"
    if themes[row["primary_theme"]]>=c["max_per_primary_theme"]: return False,"MAX_PRIMARY_THEME"
    if stages[row["business_stage"]]>=c["max_per_business_stage"]: return False,"MAX_BUSINESS_STAGE"
    for e in exposure_tokens(row["economic_exposure"]):
        if exposures[e]>=c["max_per_economic_exposure"]: return False,"MAX_ECONOMIC_EXPOSURE"
    return True,None


def select(candidates:list[dict[str,Any]], target:int, cfg:dict[str,Any], seeded_ids:list[str]|None=None) -> tuple[list[dict[str,Any]],dict[str,list[str]]]:
    by_id={x["security_id"]:x for x in candidates}; selected=[]; rejected={}
    for sid in seeded_ids or []:
        if sid in by_id and sid not in {x["security_id"] for x in selected}:
            ok,reason=allowed(by_id[sid],selected,cfg,target)
            if ok:selected.append(by_id[sid])
            else:rejected.setdefault(sid,[]).append(reason or "CONSTRAINT")
    for row in candidates:
        if len(selected)>=target:break
        if row["security_id"] in {x["security_id"] for x in selected}:continue
        ok,reason=allowed(row,selected,cfg,target)
        if ok:selected.append(row)
        else:rejected.setdefault(row["security_id"],[]).append(reason or "CONSTRAINT")
    if len(selected)<target:
        raise ValueError(f"Unable to fill target={target}; selected={len(selected)}. Relax concentration limits.")
    return selected,rejected


def retained_seed(candidates:list[dict[str,Any]], previous:dict[str,Any]|None, cfg:dict[str,Any]) -> list[str]:
    if not previous:return []
    by_id={r["security_id"]:r for r in candidates}
    rank_limit=cfg["rebalance"]["holding_buffer_rank"]
    score_gap=cfg["rebalance"]["maximum_score_gap_to_cutoff"]
    cutoff=next((r["score"] for r in candidates if r["overall_rank"]==cfg["portfolio"]["holdings_count"]),-math.inf)
    keep=[]
    for p in previous.get("holdings",[]):
        r=by_id.get(p["security_id"])
        if r and r["overall_rank"]<=rank_limit and cutoff-r["score"]<=score_gap: keep.append(r["security_id"])
    return sorted(keep,key=lambda sid:(by_id[sid]["overall_rank"],sid))


def enforce_turnover(previous:dict[str,Any]|None, selected:list[dict[str,Any]], candidates:list[dict[str,Any]], cfg:dict[str,Any]) -> list[dict[str,Any]]:
    if not previous:return selected
    old=[x["security_id"] for x in previous.get("holdings",[])]; old_set=set(old); new_set={x["security_id"] for x in selected}
    max_replacements=math.floor(cfg["portfolio"]["holdings_count"]*cfg["rebalance"]["maximum_one_way_turnover"]+1e-12)
    exits=[x for x in old if x not in new_set]
    if len(exits)<=max_replacements:return selected
    by_id={x["security_id"]:x for x in candidates}
    minimum_old=len(old)-max_replacements
    old_candidates=sorted((by_id[sid] for sid in old if sid in by_id),key=lambda r:(r["overall_rank"],r["security_id"]))
    retained_old=[]
    for row in old_candidates:
        ok,_=allowed(row,retained_old,cfg,cfg["portfolio"]["holdings_count"])
        if ok: retained_old.append(row)
        if len(retained_old)>=minimum_old: break
    if len(retained_old)<minimum_old:
        raise ValueError("Turnover cap conflicts with concentration constraints or missing prior holdings")
    revised,_=select(candidates,cfg["portfolio"]["holdings_count"],cfg,[r["security_id"] for r in retained_old])
    return revised


def assign_weights(rows:list[dict[str,Any]],cfg:dict[str,Any]) -> list[float]:
    mode=cfg["position_sizing"]["mode"]
    if mode=="equal_weight": raw=[1.0]*len(rows)
    elif mode=="score_weighted": raw=[max(r["score"],0.0)**cfg["position_sizing"].get("score_exponent",1.0) for r in rows]
    elif mode=="risk_adjusted":
        floor=cfg["position_sizing"].get("risk_score_floor",10.0)
        raw=[max(r["score"],0.0)*max(float(r["category_scores"].get("RISK") or floor),floor)/100 for r in rows]
    else: raise ValueError(f"Unsupported position sizing mode: {mode}")
    total=sum(raw); w=[x/total for x in raw]
    cap=cfg["position_sizing"]["maximum_position_weight"]
    # deterministic capped redistribution
    for _ in range(len(rows)+2):
        excess=sum(max(0,x-cap) for x in w); w=[min(x,cap) for x in w]
        if excess<1e-12:break
        room=[max(0,cap-x) for x in w]; rs=sum(room)
        if rs<=0:raise ValueError("Position cap infeasible")
        w=[x+excess*(room[i]/rs) for i,x in enumerate(w)]
    return w


def build(args:argparse.Namespace)->dict[str,Any]:
    cfg=load_json(args.config); score=load_json(args.scores); uni=load_universe(args.universe)
    previous=load_json(args.previous) if args.previous else None
    candidates=candidate_rows(score,uni)
    seed=retained_seed(candidates,previous,cfg)
    holdings,rejected=select(candidates,cfg["portfolio"]["holdings_count"],cfg,seed)
    holdings=enforce_turnover(previous,holdings,candidates,cfg)
    holding_ids={x["security_id"] for x in holdings}
    reserve_candidates=[x for x in candidates if x["security_id"] not in holding_ids]
    reserves,reserve_rejected=select(reserve_candidates,cfg["portfolio"]["reserves_count"],cfg)
    weights=assign_weights(holdings,cfg)
    old_ids={x["security_id"] for x in (previous or {}).get("holdings",[])}
    for i,(r,w) in enumerate(zip(holdings,weights),1):
        r.update({"portfolio_rank":i,"weight":round(w,10),"decision":"HOLD" if r["security_id"] in old_ids else "BUY",
                  "reason":"Retained within rebalance buffer" if r["security_id"] in seed else "Highest-ranked eligible candidate satisfying portfolio constraints"})
    for i,r in enumerate(reserves,1):
        r.update({"reserve_rank":i,"decision":"WATCH","reason":"Highest-ranked non-holding satisfying reserve constraints"})
    exits=[]
    if previous:
        for p in previous.get("holdings",[]):
            if p["security_id"] not in holding_ids: exits.append({"security_id":p["security_id"],"ticker":p.get("ticker"),"decision":"EXIT","reason":"Outside retained portfolio after ranking, buffer, constraints and turnover rules"})
    dca={r["security_id"]:round(r["weight"],10) for r in holdings}
    output={
      "engine_version":"1.0.0","as_of_date":args.as_of_date or date.today().isoformat(),
      "configuration_sha256":cfg.get("configuration_sha256") or canonical_hash({k:v for k,v in cfg.items() if k!="configuration_sha256"}),
      "source_scoring_configuration_sha256":score.get("configuration_sha256"),
      "rebalance_executed":bool(args.rebalance),"holdings":holdings,"reserves":reserves,"exits":exits,
      "dca_allocation":dca,"portfolio_summary":{"holdings_count":len(holdings),"reserves_count":len(reserves),"one_way_turnover":len(exits)/cfg["portfolio"]["holdings_count"] if previous else 0.0,
      "emerging_count":sum(r["pool"]=="Emerging" for r in holdings)},
      "audit":{"seeded_retentions":seed,"holding_constraint_rejections":rejected,"reserve_constraint_rejections":reserve_rejected}
    }
    return output


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',required=True); ap.add_argument('--universe',required=True); ap.add_argument('--scores',required=True); ap.add_argument('--output',required=True); ap.add_argument('--previous'); ap.add_argument('--as-of-date'); ap.add_argument('--rebalance',action='store_true')
    args=ap.parse_args(); out=build(args); Path(args.output).write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
if __name__=='__main__':main()
