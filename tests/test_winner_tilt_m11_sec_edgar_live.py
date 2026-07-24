from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from winner_tilt.data_providers import (
    ProviderResult,
    SecEdgarHttpsTransport,
    SecEdgarLiveRuntimeConfig,
    SecEdgarPolicyError,
    SecEdgarTransportError,
    run_authorized_pilot,
    write_immutable_snapshot,
)


FIXTURE = Path(__file__).parent / "fixtures" / "sec_edgar_companyfacts_minimal.json"


class _Response:
    status = 200

    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def _fixture_payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_runtime_config_is_offline_by_default():
    config = SecEdgarLiveRuntimeConfig.from_env({})
    assert config.enabled is False
    assert config.allowed_ciks == ()


def test_runtime_config_fails_closed_without_user_agent():
    with pytest.raises(SecEdgarPolicyError, match="SEC_EDGAR_USER_AGENT_REQUIRED"):
        SecEdgarLiveRuntimeConfig.from_env({
            "WINNER_TILT_SEC_EDGAR_LIVE_ENABLED": "true",
            "WINNER_TILT_SEC_EDGAR_CIKS": "320193",
        })


def test_runtime_kill_switch_blocks_enabled_run():
    with pytest.raises(SecEdgarPolicyError, match="SEC_EDGAR_KILL_SWITCH_ACTIVE"):
        SecEdgarLiveRuntimeConfig.from_env({
            "WINNER_TILT_SEC_EDGAR_LIVE_ENABLED": "true",
            "WINNER_TILT_SEC_EDGAR_KILL_SWITCH": "true",
            "WINNER_TILT_SEC_EDGAR_USER_AGENT": "WinnerTiltAI/1.0 ops@example.invalid",
            "WINNER_TILT_SEC_EDGAR_CIKS": "320193",
        })


def test_transport_rejects_unapproved_host():
    transport = SecEdgarHttpsTransport(opener=lambda *_args, **_kwargs: _Response({}))
    with pytest.raises(SecEdgarTransportError, match="SEC_EDGAR_UNAPPROVED_HOST"):
        transport("https://example.com/data.json", {"User-Agent": "WinnerTiltAI/1.0 ops@example.invalid"})


def test_transport_decodes_companyfacts_payload():
    payload = _fixture_payload()
    transport = SecEdgarHttpsTransport(
        opener=lambda *_args, **_kwargs: _Response(payload),
        sleeper=lambda _seconds: None,
        monotonic=lambda: 10.0,
    )
    result = transport(
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        {"User-Agent": "WinnerTiltAI/1.0 ops@example.invalid"},
    )
    assert result["cik"] == payload["cik"]


def test_snapshot_is_canonical_ingest_only_and_immutable(tmp_path):
    result = ProviderResult(
        dataset_type="fundamentals",
        rows=({"id": "row-1", "cik": "0000320193"},),
        provider_id="sec-edgar-companyfacts",
        vendor="U.S. Securities and Exchange Commission",
        acquisition_timestamp="2026-07-24T02:00:00Z",
        effective_timestamp="2025-12-31T00:00:00Z",
        schema_version="1.0.0",
        provenance={"raw_payload_retained": False},
        publication_timestamp="2026-01-30T12:00:00Z",
    )
    destination = tmp_path / "snapshot.json"
    write_immutable_snapshot(result, destination)
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["pilot_tag"] == "ingest_only_no_downstream_consumption"
    assert payload["provenance"]["raw_payload_retained"] is False
    with pytest.raises(SecEdgarPolicyError, match="SEC_EDGAR_SNAPSHOT_ALREADY_EXISTS"):
        write_immutable_snapshot(result, destination)


def test_authorized_pilot_uses_injected_transport_and_writes_isolated_snapshot(tmp_path):
    payload = _fixture_payload()
    runtime = SecEdgarLiveRuntimeConfig(
        enabled=True,
        user_agent="WinnerTiltAI/1.0 ops@example.invalid",
        allowed_ciks=("320193",),
        max_total_requests=1,
    )
    outputs = run_authorized_pilot(
        runtime,
        snapshot_dir=tmp_path,
        transport=lambda _url, _headers: payload,
        clock=lambda: datetime(2026, 7, 24, 2, 0, tzinfo=timezone.utc),
    )
    assert len(outputs) == 1
    assert outputs[0].name == "CIK0000320193.json"
    snapshot = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert snapshot["pilot_tag"] == "ingest_only_no_downstream_consumption"
    assert snapshot["provenance"]["retrieval_method"] == "https"
