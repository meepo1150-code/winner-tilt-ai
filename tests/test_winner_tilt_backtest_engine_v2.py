import json, pathlib, tempfile
from winner_tilt import backtest as bt

def test_performance_uptrend():
    m=bt.performance([100,101,102,103])
    assert m['total_return']>0 and m['max_drawdown']==0

def test_drawdown():
    m=bt.performance([100,120,90,95])
    assert round(m['max_drawdown'],4)==-0.25

def test_manifest_gate_fails_closed():
    cfg={'integrity_gates':['a','b']}
    x=bt.validate_manifest({'a':True,'b':False},cfg)
    assert not x['passed'] and x['failed']==['b']

def test_manifest_gate_passes():
    cfg={'integrity_gates':['a','b']}
    assert bt.validate_manifest({'a':True,'b':True},cfg)['passed']

def test_execution_cost():
    cfg={'costs':{'commission_bps':1,'spread_bps':2,'slippage_bps':3}}
    assert abs(bt.execution_cost(10000,cfg)-6)<1e-9

def test_membership_effective_dates():
    from datetime import date
    m={'A':[(date(2020,1,1),date(2020,12,31),'ACTIVE')]}
    assert bt.active_on(m,'A',date(2020,6,1))
    assert not bt.active_on(m,'A',date(2021,1,1))

def test_select_uses_membership_and_rank():
    from datetime import date
    rows=[{'security_id':'B','eligible':True,'total_score':90,'overall_rank':2},{'security_id':'A','eligible':True,'total_score':91,'overall_rank':1}]
    m={'A':[(date(2020,1,1),None,'ACTIVE')],'B':[(date(2020,1,1),None,'ACTIVE')]}
    assert list(bt.select_equal_weight(rows,m,date(2020,2,1),1))==['A']

def test_previous_or_equal():
    from datetime import date
    ds=[date(2020,1,1),date(2020,2,1)]
    assert bt.previous_or_equal(ds,date(2020,1,15))==date(2020,1,1)

def test_lookahead_rejected():
    raw={'vintages':[{'information_cutoff':'2020-01-31','results':[{'security_id':'A','available_at':'2020-02-01'}]}]}
    with tempfile.TemporaryDirectory() as d:
        p=pathlib.Path(d)/'x.json'; p.write_text(json.dumps(raw))
        try: bt.load_score_vintages(str(p)); assert False
        except ValueError as e: assert 'LOOKAHEAD' in str(e)

if __name__=='__main__':
    for n,o in sorted(globals().items()):
        if n.startswith('test_'): o(); print('PASS',n)
