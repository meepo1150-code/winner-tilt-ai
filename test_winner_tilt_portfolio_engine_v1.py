import argparse,copy,json,tempfile,unittest
from pathlib import Path
import winner_tilt_portfolio_engine_v1 as eng

BASE=Path('/mnt/data')
CFG=json.loads((BASE/'winner-tilt-portfolio-config-v1.0.0.json').read_text())
SCORES=json.loads((BASE/'winner-tilt-prototype-score-run-v1.0(1).json').read_text())
UNI=eng.load_universe(str(BASE/'universe-v1.0(5).csv'))

class PortfolioEngineTests(unittest.TestCase):
 def candidates(self): return eng.candidate_rows(SCORES,UNI)
 def test_candidate_order_is_deterministic(self):
  c=self.candidates(); self.assertEqual(c,sorted(c,key=lambda r:(r['overall_rank'],r['security_id'])))
 def test_selects_15_holdings(self):
  h,_=eng.select(self.candidates(),15,CFG); self.assertEqual(len(h),15); self.assertEqual(len({x['security_id'] for x in h}),15)
 def test_selects_15_reserves_excluding_holdings(self):
  c=self.candidates(); h,_=eng.select(c,15,CFG); ids={x['security_id'] for x in h}; r,_=eng.select([x for x in c if x['security_id'] not in ids],15,CFG); self.assertFalse(ids & {x['security_id'] for x in r})
 def test_concentration_limits(self):
  from collections import Counter
  h,_=eng.select(self.candidates(),15,CFG); self.assertLessEqual(sum(x['pool']=='Emerging' for x in h),CFG['concentration']['max_emerging_positions'])
  self.assertLessEqual(max(Counter(x['universe_group'] for x in h).values()),CFG['concentration']['max_per_universe_group'])
  self.assertLessEqual(max(Counter(x['primary_theme'] for x in h).values()),CFG['concentration']['max_per_primary_theme'])
  self.assertLessEqual(max(Counter(x['economic_exposure'] for x in h).values()),CFG['concentration']['max_per_economic_exposure'])
 def test_equal_weights_sum_to_one(self):
  h,_=eng.select(self.candidates(),15,CFG); w=eng.assign_weights(h,CFG); self.assertAlmostEqual(sum(w),1.0,12); self.assertTrue(all(x<=CFG['position_sizing']['maximum_position_weight']+1e-12 for x in w))
 def test_score_weighted_supported(self):
  cfg=copy.deepcopy(CFG); cfg['position_sizing']['mode']='score_weighted'; h,_=eng.select(self.candidates(),15,cfg); w=eng.assign_weights(h,cfg); self.assertAlmostEqual(sum(w),1.0,12)
 def test_risk_adjusted_supported(self):
  cfg=copy.deepcopy(CFG); cfg['position_sizing']['mode']='risk_adjusted'; h,_=eng.select(self.candidates(),15,cfg); w=eng.assign_weights(h,cfg); self.assertAlmostEqual(sum(w),1.0,12)
 def test_buffer_retains_eligible_old_holding(self):
  c=self.candidates(); previous={'holdings':[{'security_id':c[17]['security_id']}]} ; seed=eng.retained_seed(c,previous,CFG); self.assertIn(c[17]['security_id'],seed)
 def test_turnover_cap(self):
  c=self.candidates(); old_ids=[x['security_id'] for x in c[15:30]]; previous={'holdings':[{'security_id':x} for x in old_ids]}; selected,_=eng.select(c,15,CFG); revised=eng.enforce_turnover(previous,selected,c,CFG); exits=len(set(old_ids)-{x['security_id'] for x in revised}); self.assertLessEqual(exits,6)
 def test_build_contains_decisions_and_dca(self):
  args=argparse.Namespace(config=str(BASE/'winner-tilt-portfolio-config-v1.0.0.json'),universe=str(BASE/'universe-v1.0(5).csv'),scores=str(BASE/'winner-tilt-prototype-score-run-v1.0(1).json'),output='x',previous=None,as_of_date='2026-07-23',rebalance=True)
  out=eng.build(args); self.assertEqual(len(out['holdings']),15); self.assertEqual(len(out['reserves']),15); self.assertAlmostEqual(sum(out['dca_allocation'].values()),1.0,8); self.assertTrue(all(x['decision']=='BUY' for x in out['holdings']))
 def test_config_hash_is_stable(self):
  d=copy.deepcopy(CFG); expected=d.pop('configuration_sha256'); self.assertEqual(expected,eng.canonical_hash(d))
 def test_infeasible_constraints_raise(self):
  cfg=copy.deepcopy(CFG); cfg['concentration']['max_per_universe_group']=0
  with self.assertRaises(ValueError): eng.select(self.candidates(),15,cfg)

if __name__=='__main__':unittest.main(verbosity=2)
