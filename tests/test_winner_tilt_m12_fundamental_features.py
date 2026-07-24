import csv
import json
from pathlib import Path

import pytest

from winner_tilt.fundamental_features import (
    FundamentalFeatureError,
    build_fundamental_observations,
    score_vintage_metadata,
    write_scoring_observations,
)


def fact(
    identifier,
    concept,
    value,
    report_end,
    accepted,
    *,
    form="10-K",
    fiscal_period="FY",
    accession=None,
    amendment=False,
):
    return {
        "id": identifier,
        "security_id": "0000320193",
        "cik": "0000320193",
        "taxonomy": "us-gaap",
        "concept": concept,
        "unit": "USD",
        "value": value,
        "period_start": f"{int(report_end[:4]) - 1}-10-01",
        "report_end": report_end,
        "filed_date": accepted[:10],
        "accepted_timestamp": accepted,
        "accepted_timestamp_source": "accepted",
        "form": form,
        "accession_number": accession or identifier,
        "fiscal_year": int(report_end[:4]),
        "fiscal_period": fiscal_period,
        "frame": None,
        "is_amendment": amendment,
    }


DEFINITIONS = [
    {
        "metric_id": "ASSETS",
        "operation": "latest",
        "numerator_concepts": ["Assets"],
        "unit": "USD",
    },
    {
        "metric_id": "REVENUE_GROWTH",
        "operation": "growth",
        "numerator_concepts": ["Revenues"],
        "unit": "USD",
        "scale": 100,
    },
    {
        "metric_id": "NET_MARGIN",
        "operation": "ratio",
        "numerator_concepts": ["NetIncomeLoss"],
        "denominator_concepts": ["Revenues"],
        "unit": "USD",
        "scale": 100,
    },
]


def sample_facts():
    return [
        fact("assets-2024", "Assets", 1000, "2024-09-28", "2024-11-01T20:00:00Z"),
        fact("assets-2025", "Assets", 1200, "2025-09-27", "2025-10-31T20:00:00Z"),
        fact("revenue-2024", "Revenues", 400, "2024-09-28", "2024-11-01T20:00:00Z"),
        fact("revenue-2025", "Revenues", 500, "2025-09-27", "2025-10-31T20:00:00Z"),
        fact("income-2025", "NetIncomeLoss", 100, "2025-09-27", "2025-10-31T20:00:00Z"),
    ]


def by_metric(payload):
    return {row["metric_id"]: row for row in payload["observations"]}


def test_builds_latest_growth_and_ratio_for_scoring_contract():
    payload = build_fundamental_observations(
        sample_facts(),
        DEFINITIONS,
        information_cutoff="2025-11-01T00:00:00Z",
        peer_groups={"0000320193": "TECH"},
    )
    rows = by_metric(payload)
    assert rows["ASSETS"]["value"] == 1200
    assert rows["REVENUE_GROWTH"]["value"] == pytest.approx(25.0)
    assert rows["NET_MARGIN"]["value"] == pytest.approx(20.0)
    assert {row["missing_data_class"] for row in rows.values()} == {"VALID"}
    assert {row["peer_group"] for row in rows.values()} == {"TECH"}
    assert payload["downstream_contract"] == "winner_tilt.scoring_long_form_observations"


def test_point_in_time_cutoff_excludes_future_publications():
    payload = build_fundamental_observations(
        sample_facts(),
        DEFINITIONS,
        information_cutoff="2025-01-01T00:00:00Z",
    )
    rows = by_metric(payload)
    assert rows["ASSETS"]["value"] == 1000
    assert rows["REVENUE_GROWTH"]["missing_data_class"] == "TEMPORARILY_UNAVAILABLE"
    assert rows["NET_MARGIN"]["missing_data_class"] == "TEMPORARILY_UNAVAILABLE"


def test_later_amendment_replaces_original_without_lookahead():
    facts = sample_facts()
    facts.append(
        fact(
            "assets-2025-amended",
            "Assets",
            1250,
            "2025-09-27",
            "2025-11-15T20:00:00Z",
            form="10-K/A",
            accession="amended-accession",
            amendment=True,
        )
    )
    before = build_fundamental_observations(
        facts, DEFINITIONS[:1], information_cutoff="2025-11-10T00:00:00Z"
    )
    after = build_fundamental_observations(
        facts, DEFINITIONS[:1], information_cutoff="2025-11-16T00:00:00Z"
    )
    assert before["observations"][0]["value"] == 1200
    assert after["observations"][0]["value"] == 1250
    assert after["observations"][0]["source_accessions"] == ["amended-accession"]


def test_output_is_deterministic_for_reordered_facts():
    first = build_fundamental_observations(
        sample_facts(), DEFINITIONS, information_cutoff="2025-11-01T00:00:00Z"
    )
    second = build_fundamental_observations(
        list(reversed(sample_facts())), DEFINITIONS, information_cutoff="2025-11-01T00:00:00Z"
    )
    assert first["observations"] == second["observations"]
    assert first["output_sha256"] != second["output_sha256"]
    # Source hash preserves supplied snapshot ordering; business observations remain deterministic.


def test_csv_writer_emits_frozen_scoring_columns(tmp_path):
    payload = build_fundamental_observations(
        sample_facts(), DEFINITIONS, information_cutoff="2025-11-01T00:00:00Z"
    )
    output = tmp_path / "observations.csv"
    write_scoring_observations(payload, output)
    with output.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == [
        "security_id",
        "metric_id",
        "value",
        "missing_data_class",
        "peer_group",
        "stale_critical",
    ]
    assert len(rows) == 3


def test_score_vintage_metadata_carries_cutoff_and_lineage():
    payload = build_fundamental_observations(
        sample_facts(), DEFINITIONS, information_cutoff="2025-11-01T00:00:00Z"
    )
    metadata = score_vintage_metadata(payload)
    assert metadata["information_cutoff"] == "2025-11-01T00:00:00Z"
    assert metadata["generated_at"] == metadata["information_cutoff"]
    assert metadata["fundamental_feature_output_sha256"] == payload["output_sha256"]


def test_duplicate_metric_and_zero_denominators_fail_closed():
    with pytest.raises(FundamentalFeatureError, match="DUPLICATE_METRIC_ID"):
        build_fundamental_observations(
            sample_facts(), DEFINITIONS[:1] * 2, information_cutoff="2025-11-01T00:00:00Z"
        )
    zero = sample_facts()
    zero[3]["value"] = 0
    with pytest.raises(FundamentalFeatureError, match="ZERO_RATIO_DENOMINATOR"):
        build_fundamental_observations(
            zero, DEFINITIONS[2:], information_cutoff="2025-11-01T00:00:00Z"
        )


def test_invalid_or_naive_cutoff_fails_closed():
    with pytest.raises(FundamentalFeatureError, match="INVALID_CUTOFF"):
        build_fundamental_observations(sample_facts(), DEFINITIONS, information_cutoff="2025-11-01")


def test_versioned_mapping_file_is_valid():
    path = Path(__file__).parents[1] / "config" / "winner-tilt-sec-fundamental-features-v1.0.0.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == "1.0.0"
    payload = build_fundamental_observations(
        sample_facts(), raw["features"], information_cutoff="2025-11-01T00:00:00Z"
    )
    assert len(payload["observations"]) == len(raw["features"])
