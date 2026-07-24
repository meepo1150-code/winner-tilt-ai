import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from winner_tilt.data_providers.sec_edgar import (
    SecEdgarCompanyFactsProvider,
    SecEdgarPilotConfig,
    SecEdgarPolicyError,
    normalize_companyfacts,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sec_edgar_companyfacts_minimal.json"
NOW = datetime(2026, 7, 24, 0, 0, tzinfo=timezone.utc)


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def config(**overrides):
    values = {
        "allowed_ciks": ("0000320193",),
        "live_enabled": False,
        "max_requests_per_second": 2.0,
        "retain_raw_payload": False,
    }
    values.update(overrides)
    return SecEdgarPilotConfig(**values)


def test_fixture_normalizes_deterministically_and_preserves_amendment_lineage():
    rows1 = normalize_companyfacts(load_fixture(), expected_cik="320193")
    rows2 = normalize_companyfacts(load_fixture(), expected_cik="0000320193")
    assert rows1 == rows2
    assert len(rows1) == 2
    assert rows1[0]["accession_number"] != rows1[1]["accession_number"]
    assert {row["is_amendment"] for row in rows1} == {False, True}


def test_provider_is_offline_by_default_and_ingest_only():
    provider = SecEdgarCompanyFactsProvider(config(), clock=lambda: NOW)
    result = provider.fetch(cik="320193", payload=load_fixture())
    assert result.dataset_type == "fundamentals"
    assert result.provider_id == "sec-edgar-companyfacts"
    assert result.provenance["raw_payload_retained"] is False
    assert result.provenance["pilot_scope"] == "ingest_only_no_downstream_consumption"
    assert provider.latest_timestamp() == "2026-07-21T20:00:00Z"
    assert provider.validate(result).status == "PASS"


def test_live_mode_requires_user_agent_and_transport():
    with pytest.raises(SecEdgarPolicyError, match="USER_AGENT_REQUIRED"):
        SecEdgarCompanyFactsProvider(config(live_enabled=True))
    provider = SecEdgarCompanyFactsProvider(config(live_enabled=True, user_agent="WinnerTilt/1.0 contact@example.invalid"))
    with pytest.raises(SecEdgarPolicyError, match="TRANSPORT_REQUIRED"):
        provider.fetch(cik="320193")


def test_allowlist_rate_and_retention_policies_fail_closed():
    with pytest.raises(SecEdgarPolicyError, match="RATE_LIMIT"):
        SecEdgarCompanyFactsProvider(config(max_requests_per_second=2.1))
    with pytest.raises(SecEdgarPolicyError, match="RAW_RETENTION"):
        SecEdgarCompanyFactsProvider(config(retain_raw_payload=True))
    provider = SecEdgarCompanyFactsProvider(config(), clock=lambda: NOW)
    with pytest.raises(SecEdgarPolicyError, match="NOT_ALLOWLISTED"):
        provider.fetch(cik="789019", payload=load_fixture())


def test_duplicate_natural_key_and_missing_acceptance_fail_closed():
    payload = load_fixture()
    duplicate = dict(payload["facts"]["us-gaap"]["Assets"]["units"]["USD"][0])
    payload["facts"]["us-gaap"]["Assets"]["units"]["USD"].append(duplicate)
    with pytest.raises(SecEdgarPolicyError, match="DUPLICATE_NATURAL_KEY"):
        normalize_companyfacts(payload, expected_cik="320193")

    payload = load_fixture()
    del payload["facts"]["us-gaap"]["Assets"]["units"]["USD"][0]["accepted"]
    with pytest.raises(SecEdgarPolicyError, match="ACCEPTED_TIMESTAMP_REQUIRED"):
        normalize_companyfacts(payload, expected_cik="320193")


def test_transport_receives_declared_user_agent():
    calls = []

    def transport(url, headers):
        calls.append((url, headers))
        return load_fixture()

    provider = SecEdgarCompanyFactsProvider(
        config(live_enabled=True, user_agent="WinnerTilt/1.0 ops@example.invalid"),
        transport=transport,
        clock=lambda: NOW,
    )
    provider.fetch(cik="320193")
    assert calls[0][1]["User-Agent"].startswith("WinnerTilt/1.0")
