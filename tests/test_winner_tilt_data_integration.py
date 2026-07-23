from winner_tilt import data_integration


def snapshot(**overrides):
    raw = {
        "universe": [
            {"security_id": "WT-S0001", "ticker": "AAA", "name": "Alpha", "sector": "Software", "active": "true"},
        ],
        "metrics": [
            {"security_id": "WT-S0001", "metric_id": "revenue_growth", "as_of_date": "2026-07-20", "value": "0.21", "source_name": "Vendor", "source_tier": "VENDOR", "ingested_at": "2026-07-20T12:00:00Z"},
        ],
        "events": [
            {"event_id": "EV-001", "event_type": "GUIDANCE_CHANGE", "security_id": "WT-S0001", "published_at": "2026-07-20T13:00:00Z", "source_name": "Issuer IR", "source_tier": "PRIMARY"},
        ],
    }
    raw.update(overrides)
    return raw


def run(snap):
    return data_integration.validate_production_snapshot(snap, information_cutoff="2026-07-23T00:00:00Z")


def test_valid_snapshot_passes_with_non_interference():
    out = run(snapshot())
    assert out["run_status"] == "PASS"
    assert out["counts"]["metrics"]["accepted"] == 1
    assert not any(out["non_interference"].values())


def test_future_metric_fails_closed():
    snap = snapshot(metrics=[{"security_id": "WT-S0001", "metric_id": "revenue_growth", "as_of_date": "2026-07-24", "value": "0.21", "source_name": "Vendor", "source_tier": "VENDOR", "ingested_at": "2026-07-20T12:00:00Z"}])
    out = run(snap)
    assert out["run_status"] == "FAIL_CLOSED"
    assert "AS_OF_DATE_AFTER_CUTOFF" in out["rejected_rows"][0]["errors"]


def test_unknown_security_rejected():
    snap = snapshot(events=[{"event_id": "EV-001", "event_type": "GUIDANCE_CHANGE", "security_id": "WT-S9999", "published_at": "2026-07-20T13:00:00Z", "source_name": "Issuer IR", "source_tier": "PRIMARY"}])
    out = run(snap)
    assert "UNKNOWN_OR_INACTIVE_SECURITY_ID" in out["rejected_rows"][0]["errors"]


def test_duplicate_natural_key_rejected():
    row = {"security_id": "WT-S0001", "metric_id": "revenue_growth", "as_of_date": "2026-07-20", "value": "0.21", "source_name": "Vendor", "source_tier": "VENDOR", "ingested_at": "2026-07-20T12:00:00Z"}
    out = run(snapshot(metrics=[row, dict(row)]))
    assert out["counts"]["metrics"]["accepted"] == 1
    assert "DUPLICATE_NATURAL_KEY" in out["rejected_rows"][0]["errors"]


def test_deterministic_output_hash():
    a = run(snapshot())
    b = run(snapshot())
    assert a["output_sha256"] == b["output_sha256"]
