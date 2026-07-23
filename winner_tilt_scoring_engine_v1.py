#!/usr/bin/env python3
"""Winner Tilt AI deterministic prototype scoring engine v1.0.
Input observations CSV columns:
security_id,metric_id,value,missing_data_class,peer_group,stale_critical
Missing class: VALID, NOT_APPLICABLE, TEMPORARILY_UNAVAILABLE, STRUCTURALLY_UNSUPPORTED.
"""
from __future__ import annotations
import argparse,csv,json,math,hashlib
from collections import defaultdict
from pathlib import Path

def percentile(values, x):
    vals=sorted(values)
    if not vals: return None
    if len(vals)==1: return 50.0
    less=sum(v<x for v in vals); equal=sum(v==x for v in vals)
    return 100.0*(less+0.5*equal)/len(vals)

def quantile(vals,q):
    s=sorted(vals)
    if not s:return None
    p=(len(s)-1)*q; lo=int(math.floor(p)); hi=int(math.ceil(p))
    return s[lo] if lo==hi else s[lo]+(s[hi]-s[lo])*(p-lo)

def stage_ok(module,stage):
    return module in ('ALL','NON_FINANCIALS') or stage==module or (module=='GRW_MAT' and stage in ('GRW','MAT'))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',required=True); ap.add_argument('--universe',required=True); ap.add_argument('--observations',required=True); ap.add_argument('--output',required=True)
    a=ap.parse_args(); cfg=json.loads(Path(a.config).read_text())
    universe={}
    with open(a.universe,newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f): universe[r['WT_ID']]={'ticker':r['Ticker'],'stage':{'Emerging':'EMG','Growth':'GRW','Mature':'MAT'}[r['Business_Stage']]}
    obs={}
    with open(a.observations,newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            r['value']=None if r['value']=='' else float(r['value']); r['stale_critical']=r.get('stale_critical','').lower()=='true'; obs[(r['security_id'],r['metric_id'])]=r
    metrics={m['metric_id']:m for m in cfg['metrics']}
    valid_by_metric=defaultdict(list); valid_by_peer=defaultdict(list)
    for (sid,mid),r in obs.items():
        if sid in universe and mid in metrics and r['missing_data_class']=='VALID' and r['value'] is not None:
            valid_by_metric[mid].append(r['value']); valid_by_peer[(mid,r.get('peer_group',''))].append(r['value'])
    out=[]
    for sid,u in universe.items():
        cats=defaultdict(list); unavailable_weight=0; stale_count=0; weighted_available=0; weighted_total=0; flags=[]
        for mid,m in metrics.items():
            if not stage_ok(m['stage_module'],u['stage']): continue
            cat_weight=cfg['stage_category_weights'][u['stage']][m['category']]; base=m['default_weight']; global_w=cat_weight*base; weighted_total+=global_w
            r=obs.get((sid,mid),{'missing_data_class':'TEMPORARILY_UNAVAILABLE','value':None,'peer_group':'','stale_critical':False})
            cls=r['missing_data_class']; score=None
            if cls=='VALID' and r['value'] is not None:
                vals=valid_by_metric[mid]; lo=quantile(vals,cfg['normalization']['winsor_lower']); hi=quantile(vals,cfg['normalization']['winsor_upper']); x=min(max(r['value'],lo),hi)
                up=percentile([min(max(v,lo),hi) for v in vals],x)
                pv=valid_by_peer[(mid,r.get('peer_group',''))]
                if len(pv)>=cfg['normalization']['minimum_peer_count']:
                    plo=quantile(pv,cfg['normalization']['winsor_lower']); phi=quantile(pv,cfg['normalization']['winsor_upper']); pp=percentile([min(max(v,plo),phi) for v in pv],min(max(r['value'],plo),phi)); score=.7*pp+.3*up
                else: score=up; flags.append('SMALL_PEER_GROUP:'+mid)
                if not m['higher_is_better']: score=100-score
                weighted_available+=global_w
            elif cls=='TEMPORARILY_UNAVAILABLE': score=50.0; unavailable_weight+=global_w; stale_count+=int(r.get('stale_critical',False))
            elif cls=='STRUCTURALLY_UNSUPPORTED': flags.append('STRUCTURALLY_UNSUPPORTED:'+mid)
            cats[m['category']].append((mid,base,score,cls))
        category_scores={}; category_cov={}
        eligible=True
        for cat,items in cats.items():
            applicable=[x for x in items if x[3] != 'NOT_APPLICABLE']
            scored=[x for x in applicable if x[2] is not None]
            denom=sum(x[1] for x in applicable); category_cov[cat]=(sum(x[1] for x in scored)/denom if denom else 0)
            category_scores[cat]=(sum(x[1]*x[2] for x in scored)/sum(x[1] for x in scored)) if scored else None
            if cfg['stage_category_weights'][u['stage']][cat]>=cfg['missing_data']['major_category_weight_threshold'] and category_cov[cat]<cfg['missing_data']['minimum_major_category_coverage']: eligible=False; flags.append('LOW_CATEGORY_COVERAGE:'+cat)
        total_cov=weighted_available/weighted_total if weighted_total else 0
        if total_cov<cfg['missing_data']['minimum_total_weighted_coverage']: eligible=False; flags.append('LOW_TOTAL_COVERAGE')
        penalty=min(cfg['missing_data']['maximum_penalty'], cfg['missing_data']['penalty_per_unavailable_weight_pct']*(unavailable_weight*100)+cfg['missing_data']['stale_critical_metric_penalty']*stale_count)
        pre=sum((category_scores[c] or 0)*w for c,w in cfg['stage_category_weights'][u['stage']].items())
        total=max(0,min(100,pre-penalty)) if eligible else None
        out.append({'security_id':sid,'ticker':u['ticker'],'stage':u['stage'],'eligible':eligible,'total_score':total,'penalty_score':penalty,'weighted_coverage':total_cov,'category_scores':category_scores,'flags':sorted(set(flags))})
    eligible=[x for x in out if x['eligible']]
    eligible.sort(key=lambda x:(-(x['total_score'] or -1),-(x['category_scores'].get('QUALITY') or -1),-(x['category_scores'].get('FINANCIAL_STRENGTH') or -1),x['security_id']))
    ranks={x['security_id']:i+1 for i,x in enumerate(eligible)}
    for x in out: x['overall_rank']=ranks.get(x['security_id']); x['rank_status']='INELIGIBLE' if not x['eligible'] else 'WATCH'  # portfolio/reserve state is assigned by Portfolio Engine
    Path(a.output).write_text(json.dumps({'configuration_sha256':cfg['configuration_sha256'],'results':out},indent=2),encoding='utf-8')
if __name__=='__main__': main()
