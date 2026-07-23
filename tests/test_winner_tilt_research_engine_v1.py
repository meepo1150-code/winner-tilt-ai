import json
import pathlib

from winner_tilt import research

BASE = pathlib.Path(__file__).resolve().parent
CFG = json.loads((BASE.parents[0] / "config" / "winner-tilt-research-config-v1.0.0.json").read_text())


def event(**overrides):
    raw = {
        "event_id": "EV-001",
        "event_type": "GUIDANCE_CHANGE",
        "title": "Company raises guidance",
        "summary": "Example deterministic event",
        "direction": "POSITIVE",
        "severity": 4,
        "confidence": 0.9,
        "event_time": "2026-07-20T12:00:00Z",
        "published_at": "2026-07-20T13:00:00Z",
        "ingested_at": "2026-07-20T13:05:00Z",
        "source_name": "Issuer IR",
        "source_tier": "PRIMARY",
        "source_url": "https://example.invalid/event",
        "source_external_id": "issuer-001",
        "security_ids": ["WT-S0001"],
        "unverified": False,
    }
    raw.update(overrides)
    return raw


def test_accepts_valid_event():
    out = research.run_research([event()], CFG, "2026-07-23T00:00:00Z")
    assert out["counts"]["accepted"] == 1
    assert out["security_summaries"][0]["context_label"] == "POSITIVE_CONTEXT"


def test_rejects_lookahead_publication():
    out = research.run_research([event(published_at="2026-07-24T00:00:00Z", ingested_at="2026-07-24T00:01:00Z")], CFG, "2026-07-23T00:00:00Z")
    assert out["counts"]["rejected"] == 1
    assert "PUBLICATION_AFTER_CUTOFF" in out["rejected_events"][0]["errors"]


def test_rejects_ingestion_before_publication():
    out = research.run_research([event(ingested_at="2026-07-20T12:59:00Z")], CFG, "2026-07-23T00:00:00Z")
    assert "INGESTED_BEFORE_PUBLISHED" in out["rejected_events"][0]["errors"]


def test_rejects_naive_timestamp():
    out = research.run_research([event(published_at="2026-07-20T13:00:00")], CFG, "2026-07-23T00:00:00Z")
    assert any("TIMEZONE_REQUIRED" in x for x in out["rejected_events"][0]["errors"])


def test_duplicate_fingerprint():
    second = event(event_id="EV-002")
    out = research.run_research([event(), second], CFG, "2026-07-23T00:00:00Z")
    assert out["counts"]["accepted"] == 1 and out["counts"]["duplicates"] == 1


def test_negative_signal():
    out = research.run_research([event(direction="NEGATIVE", title="Guidance reduced")], CFG, "2026-07-23T00:00:00Z")
    assert out["security_summaries"][0]["research_signal"] < 0
    assert out["security_summaries"][0]["context_label"] == "NEGATIVE_CONTEXT"


def test_mixed_context():
    a = event()
    b = event(event_id="EV-002", source_external_id="issuer-002", title="Company reduces another target", direction="NEGATIVE")
    out = research.run_research([a, b], CFG, "2026-07-23T00:00:00Z")
    assert out["security_summaries"][0]["context_label"] == "MIXED_CONTEXT"


def test_unverified_confidence_cap():
    out = research.run_research([event(unverified=True, source_tier="UNVERIFIED", confidence=0.8)], CFG, "2026-07-23T00:00:00Z")
    assert "UNVERIFIED_CONFIDENCE_TOO_HIGH" in out["rejected_events"][0]["errors"]


def test_non_interference_contract():
    out = research.run_research([event()], CFG, "2026-07-23T00:00:00Z")
    assert not any(out["non_interference"].values())


def test_deterministic_hash():
    a = research.run_research([event()], CFG, "2026-07-23T00:00:00Z")
    b = research.run_research([event()], CFG, "2026-07-23T00:00:00Z")
    assert a["output_sha256"] == b["output_sha256"]


if __name__ == "__main__":
    for name, obj in sorted(globals().items()):
        if name.startswith("test_"):
            obj()
            print("PASS", name)
