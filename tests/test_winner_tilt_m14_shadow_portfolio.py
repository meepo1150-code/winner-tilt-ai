import csv
import json
from pathlib import Path

import pytest

from winner_tilt.shadow_portfolio import ShadowPortfolioError, certify_vintage, run_shadow_portfolio


def write_json(path: Path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def vintage_payload(certified=True):
    results=[]
    for index,(sid,ticker,score) in enumerate((("WT-0001","AAA",90.0),("WT-0002","BBB",80.0)),1):
        results.append({"security_id":sid,"ticker":ticker,"stage":"MAT","eligible":True,"total_score":score,
                        "penalty_score":0.0,"weighted_coverage":1.0,"category_scores":{"QUALITY":score},
                        "flags":[],"overall_rank":index,"rank_status":"WATCH","available_at":"2026-01-31T00:00:00Z"})
    vintage={"information_cutoff":"2026-02-01T00:00:00Z","generated_at":"2026-02-01T00:00:00Z",
             "certification":{"status":"CERTIFIED" if certified else "BLOCKED"},"lineage":[{"name":"source","sha256":"a"*64}],
             "scoring_configuration_sha256":"score-cfg","results":results}
    return {"vintages":[vintage]}


def files(tmp_path):
    vintage=tmp_path/"vintage.json"; write_json(vintage,vintage_payload())
    cfg=tmp_path/"portfolio.json"; write_json(cfg,{
        "portfolio":{"holdings_count":1,"reserves_count":1},
        "concentration":{"max_emerging_positions":1,"max_per_universe_group":2,"max_per_primary_theme":2,
                         "max_per_business_stage":2,"max_per_economic_exposure":2},
        "rebalance":{"holding_buffer_rank":1,"maximum_score_gap_to_cutoff":0.0,"maximum_one_way_turnover":1.0},
        "position_sizing":{"mode":"equal_weight","maximum_position_weight":1.0},
    })
    universe=tmp_path/"universe.csv"
    fields=["WT_ID","Ticker","Pool","Business_Stage","Universe_Group","Primary_Theme","Economic_Exposure","Quality_Tier"]
    with universe.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields); writer.writeheader()
        writer.writerow({"WT_ID":"WT-0001","Ticker":"AAA","Pool":"Core","Business_Stage":"Mature","Universe_Group":"G1","Primary_Theme":"T1","Economic_Exposure":"E1","Quality_Tier":"A"})
        writer.writerow({"WT_ID":"WT-0002","Ticker":"BBB","Pool":"Core","Business_Stage":"Mature","Universe_Group":"G2","Primary_Theme":"T2","Economic_Exposure":"E2","Quality_Tier":"A"})
    return vintage,cfg,universe


def test_uncertified_vintage_fails_closed():
    with pytest.raises(ShadowPortfolioError,match="SHADOW_PORTFOLIO_UNCERTIFIED_VINTAGE"):
        certify_vintage(vintage_payload(False),as_of_date="2026-02-01")


def test_future_cutoff_fails_closed():
    payload=vintage_payload(); payload["vintages"][0]["information_cutoff"]="2026-02-02T00:00:00Z"
    with pytest.raises(ShadowPortfolioError,match="SHADOW_PORTFOLIO_FUTURE_CUTOFF"):
        certify_vintage(payload,as_of_date="2026-02-01")


def test_duplicate_rank_fails_closed():
    payload=vintage_payload(); payload["vintages"][0]["results"][1]["overall_rank"]=1
    with pytest.raises(ShadowPortfolioError,match="SHADOW_PORTFOLIO_DUPLICATE_RANK"):
        certify_vintage(payload,as_of_date="2026-02-01")


def test_end_to_end_shadow_portfolio_uses_real_portfolio_cli(tmp_path):
    vintage,cfg,universe=files(tmp_path)
    result=run_shadow_portfolio(vintage_path=vintage,portfolio_config_path=cfg,universe_path=universe,as_of_date="2026-02-01")
    assert result["mode"]=="SHADOW_RESEARCH_ONLY"
    assert result["portfolio"]["holdings"][0]["security_id"]=="WT-0001"
    assert result["portfolio"]["reserves"][0]["security_id"]=="WT-0002"
    assert result["portfolio"]["holdings"][0]["weight"]==1.0
    assert result["execution_boundary"]=={"broker_connected":False,"orders_created":False,"orders_executed":False,"automatic_dca":False,"automatic_exits":False}


def test_output_is_deterministic(tmp_path):
    vintage,cfg,universe=files(tmp_path)
    kwargs=dict(vintage_path=vintage,portfolio_config_path=cfg,universe_path=universe,as_of_date="2026-02-01")
    assert run_shadow_portfolio(**kwargs)==run_shadow_portfolio(**kwargs)
