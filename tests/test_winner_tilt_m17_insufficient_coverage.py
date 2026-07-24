import csv
import json
from pathlib import Path

from winner_tilt.shadow_portfolio import run_shadow_portfolio


def _write_json(path: Path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def _lineage():
    return {
        "pipeline_version": "1.0.0",
        "snapshot_file_sha256": "a" * 64,
        "snapshot_payload_sha256": "b" * 64,
        "raw_content_sha256": "c" * 64,
        "identifier_registry_sha256": "d" * 64,
        "feature_definitions_sha256": "e" * 64,
        "fundamental_feature_output_sha256": "f" * 64,
        "scoring_config_sha256": "1" * 64,
        "universe_sha256": "2" * 64,
        "scoring_output_sha256": "3" * 64,
    }


def test_single_security_live_vintage_returns_non_executable_coverage_artifact(tmp_path):
    vintage = tmp_path / "vintage.json"
    _write_json(vintage, {
        "vintages": [{
            "information_cutoff": "2026-07-24T05:45:00Z",
            "generated_at": "2026-07-24T05:45:00Z",
            "certification": {"status": "CERTIFIED"},
            "lineage": _lineage(),
            "results": [{
                "security_id": "WT-0005",
                "ticker": "AAPL",
                "eligible": False,
                "total_score": None,
                "overall_rank": None,
                "available_at": "2026-07-23T20:00:00Z",
                "flags": ["INSUFFICIENT_FEATURE_COVERAGE"],
            }],
        }]
    })
    config = tmp_path / "portfolio.json"
    _write_json(config, {
        "portfolio": {"holdings_count": 15, "reserves_count": 15},
        "concentration": {
            "max_emerging_positions": 3,
            "max_per_universe_group": 4,
            "max_per_primary_theme": 3,
            "max_per_economic_exposure": 3,
            "max_per_business_stage": 10,
        },
        "rebalance": {
            "holding_buffer_rank": 20,
            "maximum_score_gap_to_cutoff": 5.0,
            "maximum_one_way_turnover": 0.4,
        },
        "position_sizing": {"mode": "equal_weight", "maximum_position_weight": 0.08},
    })
    universe = tmp_path / "universe.csv"
    fields = ["WT_ID", "Ticker", "Pool", "Business_Stage", "Universe_Group", "Primary_Theme", "Economic_Exposure", "Quality_Tier"]
    with universe.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow({
            "WT_ID": "WT-0005", "Ticker": "AAPL", "Pool": "Core", "Business_Stage": "Mature",
            "Universe_Group": "Platforms", "Primary_Theme": "Consumer Technology",
            "Economic_Exposure": "Consumer spending", "Quality_Tier": "S",
        })

    result = run_shadow_portfolio(
        vintage_path=vintage,
        portfolio_config_path=config,
        universe_path=universe,
        as_of_date="2026-07-24",
    )

    portfolio = result["portfolio"]
    assert portfolio["construction_status"] == "INSUFFICIENT_COVERAGE_RESEARCH_ONLY"
    assert portfolio["holdings"] == []
    assert portfolio["reserves"] == []
    assert portfolio["dca_allocation"] == {}
    assert portfolio["portfolio_summary"]["eligible_candidate_count"] == 0
    assert portfolio["portfolio_summary"]["required_candidate_count"] == 30
    assert portfolio["audit"]["portfolio_engine_executed"] is False
    assert portfolio["audit"]["frozen_portfolio_rules_modified"] is False
    assert all(value is False for value in result["execution_boundary"].values())
