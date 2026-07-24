import csv
import json
from pathlib import Path

import pytest

from winner_tilt.backtest import load_score_vintages
from winner_tilt.sec_to_score import (
    SecToScoreError,
    certify_snapshot,
    load_identifier_registry,
    run_pipeline,
)


def fact(*, accepted="2026-01-31T12:00:00Z", cik="0000320193"):
    return {
        "id": f"{cik}:us-gaap:Assets:USD:abc",
        "security_id": cik,
        "cik": cik,
        "taxonomy": "us-gaap",
        "concept": "Assets",
        "unit": "USD",
        "value": 1000.0,
        "period_start": None,
        "report_end": "2025-12-31",
        "filed_date": "2026-01-31",
        "accepted_timestamp": accepted,
        "accepted_timestamp_source": "accepted",
        "form": "10-K",
        "accession_number": "0000320193-26-000001",
        "fiscal_year": 2025,
        "fiscal_period": "FY",
        "frame": "CY2025Q4I",
        "is_amendment": False,
    }


def snapshot(rows=None):
    return {
        "dataset_type": "fundamentals",
        "rows": rows or [fact()],
        "provider_id": "sec-edgar-companyfacts",
        "vendor": "U.S. Securities and Exchange Commission",
        "acquisition_timestamp": "2026-02-01T00:00:00Z",
        "effective_timestamp": "2025-12-31T00:00:00Z",
        "schema_version": "1.0.0",
        "provenance": {
            "source_reference": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            "retrieval_method": "https",
            "raw_content_sha256": "a" * 64,
            "raw_payload_retained": False,
        },
        "validation_state": "unvalidated",
        "publication_timestamp": "2026-01-31T12:00:00Z",
        "pilot_tag": "ingest_only_no_downstream_consumption",
    }


def write_json(path: Path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def pipeline_files(tmp_path: Path):
    snapshot_path = tmp_path / "snapshot.json"
    write_json(snapshot_path, snapshot())

    registry_path = tmp_path / "identifiers.csv"
    registry_path.write_text(
        "cik,security_id,ticker,status,effective_from,effective_to,source\n"
        "0000320193,WT-0005,AAPL,ACTIVE,2026-01-01,,test\n",
        encoding="utf-8",
    )

    definitions_path = tmp_path / "features.json"
    write_json(definitions_path, {
        "features": [{
            "metric_id": "TOTAL_ASSETS",
            "operation": "latest",
            "numerator_concepts": ["Assets"],
            "unit": "USD",
            "forms": ["10-K"],
            "stale_after_days": 550,
        }]
    })

    scoring_path = tmp_path / "scoring.json"
    write_json(scoring_path, {
        "configuration_sha256": "test-scoring-config",
        "metrics": [{
            "metric_id": "TOTAL_ASSETS",
            "category": "QUALITY",
            "stage_module": "ALL",
            "default_weight": 1.0,
            "higher_is_better": True,
        }],
        "stage_category_weights": {
            "EMG": {"QUALITY": 1.0},
            "GRW": {"QUALITY": 1.0},
            "MAT": {"QUALITY": 1.0},
        },
        "normalization": {
            "winsor_lower": 0.05,
            "winsor_upper": 0.95,
            "minimum_peer_count": 3,
        },
        "missing_data": {
            "major_category_weight_threshold": 0.2,
            "minimum_major_category_coverage": 0.5,
            "minimum_total_weighted_coverage": 0.5,
            "maximum_penalty": 30.0,
            "penalty_per_unavailable_weight_pct": 0.0,
            "stale_critical_metric_penalty": 0.0,
        },
    })

    universe_path = tmp_path / "universe.csv"
    with universe_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["WT_ID", "Ticker", "Business_Stage"])
        writer.writeheader()
        writer.writerow({"WT_ID": "WT-0005", "Ticker": "AAPL", "Business_Stage": "Mature"})
    return snapshot_path, registry_path, definitions_path, scoring_path, universe_path


def test_snapshot_is_recertified_instead_of_trusting_embedded_state():
    result = certify_snapshot(snapshot(), "2026-02-01T00:00:00Z")
    assert result["status"] == "CERTIFIED"
    assert result["row_count"] == 1


def test_future_fact_fails_closed():
    with pytest.raises(SecToScoreError, match="SEC_TO_SCORE_FUTURE_FACT"):
        certify_snapshot(snapshot([fact(accepted="2026-02-02T00:00:00Z")]), "2026-02-01T00:00:00Z")


def test_identifier_registry_requires_one_to_one_active_links(tmp_path):
    path = tmp_path / "ids.csv"
    path.write_text(
        "cik,security_id,ticker,status,effective_from,effective_to,source\n"
        "0000320193,WT-0005,AAPL,ACTIVE,2026-01-01,,test\n"
        "0000789019,WT-0005,MSFT,ACTIVE,2026-01-01,,test\n",
        encoding="utf-8",
    )
    with pytest.raises(SecToScoreError, match="SEC_TO_SCORE_IDENTIFIER_NOT_ONE_TO_ONE"):
        load_identifier_registry(path)


def test_full_pipeline_emits_backtest_compatible_certified_vintage(tmp_path):
    paths = pipeline_files(tmp_path)
    result = run_pipeline(
        snapshot_path=paths[0],
        identifier_registry_path=paths[1],
        feature_definitions_path=paths[2],
        scoring_config_path=paths[3],
        universe_path=paths[4],
        information_cutoff="2026-02-01T00:00:00Z",
    )
    vintage = result["vintages"][0]
    assert vintage["certification"]["status"] == "CERTIFIED"
    assert vintage["results"][0]["security_id"] == "WT-0005"
    assert vintage["results"][0]["available_at"] == "2026-01-31T12:00:00Z"
    assert vintage["results"][0]["total_score"] == 50.0
    assert vintage["safety_boundary"]["portfolio_consumption"] is False
    assert len(vintage["lineage"]) == 10

    output = tmp_path / "vintages.json"
    write_json(output, result)
    loaded = load_score_vintages(str(output))
    assert list(loaded.values())[0][0]["security_id"] == "WT-0005"


def test_pipeline_output_is_deterministic(tmp_path):
    paths = pipeline_files(tmp_path)
    kwargs = dict(
        snapshot_path=paths[0], identifier_registry_path=paths[1],
        feature_definitions_path=paths[2], scoring_config_path=paths[3],
        universe_path=paths[4], information_cutoff="2026-02-01T00:00:00Z",
    )
    assert run_pipeline(**kwargs) == run_pipeline(**kwargs)


def test_unmapped_cik_is_blocked(tmp_path):
    paths = pipeline_files(tmp_path)
    bad = snapshot([fact(cik="0000789019")])
    write_json(paths[0], bad)
    with pytest.raises(SecToScoreError, match="SEC_TO_SCORE_UNMAPPED_CIK"):
        run_pipeline(
            snapshot_path=paths[0], identifier_registry_path=paths[1],
            feature_definitions_path=paths[2], scoring_config_path=paths[3],
            universe_path=paths[4], information_cutoff="2026-02-01T00:00:00Z",
        )
