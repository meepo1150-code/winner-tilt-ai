#!/usr/bin/env python3
"""Winner Tilt AI prototype point-in-time walk-forward backtest interface v1.0.
Not production-valid unless supplied data satisfy the Data Sources v1.0 PIT rules.
"""
from __future__ import annotations
import argparse,csv,json,math
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def load_prices(path):
    by=defaultdict(dict)
    with open(path,newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f): by[r['date']][r['security_id']]=float(r['adjusted_close'])
    return dict(sorted(by.items()))

def metrics(values,turnover=0.0):
    if len(values)<2:return {"cagr":None,"annualized_volatility":None,"sharpe":None,"sortino":None,"max_drawdown":None,"turnover":turnover}
    rets=[values[i]/values[i-1]-1 for i in range(1,len(values))]
    years=max((len(values)-1)/252,1/252); cagr=(values[-1]/values[0])**(1/years)-1
    mean=sum(rets)/len(rets); var=sum((x-mean)**2 for x in rets)/max(1,len(rets)-1); vol=math.sqrt(var)*math.sqrt(252)
    downside=[min(x,0) for x in rets]; dvar=sum(x*x for x in downside)/max(1,len(downside)); dvol=math.sqrt(dvar)*math.sqrt(252)
    peak=values[0]; mdd=0
    for v in values: peak=max(peak,v); mdd=min(mdd,v/peak-1)
    return {"cagr":cagr,"annualized_return":mean*252,"annualized_volatility":vol,"sharpe":mean*252/vol if vol else None,"sortino":mean*252/dvol if dvol else None,"max_drawdown":mdd,"turnover":turnover}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--portfolio',required=True); ap.add_argument('--prices',required=True); ap.add_argument('--output',required=True); ap.add_argument('--initial-capital',type=float,default=100000); ap.add_argument('--commission-bps',type=float,default=0); ap.add_argument('--slippage-bps',type=float,default=0)
    a=ap.parse_args(); p=json.load(open(a.portfolio)); prices=load_prices(a.prices); holdings={x['security_id']:x['weight'] for x in p['holdings']}
    dates=[d for d,row in prices.items() if all(s in row for s in holdings)]
    if not dates:raise ValueError('No dates contain all portfolio securities')
    first=prices[dates[0]]; cost=(a.commission_bps+a.slippage_bps)/10000; capital=a.initial_capital*(1-cost)
    shares={s:capital*w/first[s] for s,w in holdings.items()}; curve=[]
    for d in dates: curve.append({'date':d,'portfolio_value':sum(shares[s]*prices[d][s] for s in shares)})
    vals=[x['portfolio_value'] for x in curve]; out={'interface_version':'1.0.0','validation_status':'PROTOTYPE_ONLY','warning':'Production use requires point-in-time fundamentals, constituents, estimates and delisted securities.','metrics':metrics(vals,p.get('portfolio_summary',{}).get('one_way_turnover',0)),'equity_curve':curve}
    Path(a.output).write_text(json.dumps(out,indent=2),encoding='utf-8')
if __name__=='__main__':main()
