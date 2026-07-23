#!/usr/bin/env python3
"""Winner Tilt AI deterministic Research Engine v1.0.

Validates timestamped research events, enforces a point-in-time cutoff, detects
canonical duplicates, and produces informational security context. The output
cannot alter scoring, portfolio construction, DCA allocation, or backtests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ENGINE_VERSION = "1.0.0"


def load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def parse_ts(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"MISSING_{field.upper()}")
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"INVALID_{field.upper()}") from exc
    if dt.tzinfo is None:
        raise ValueError(f"TIMEZONE_REQUIRED_{field.upper()}")
    return dt.astimezone(timezone.utc)


def fingerprint(event: dict[str, Any]) -> str:
    identity = {
        "source_name": event.get("source_name"),
        "source_external_id": event.get("source_external_id"),
        "event_type": event.get("event_type"),
        "published_at": event.get("published_at"),
        "title": event.get("title"),
        "security_ids": sorted(event.get("security_ids") or []),
    }
    return canonical_hash(identity)


def validate_event(event: dict[str, Any], cfg: dict[str, Any], cutoff: datetime) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    required = ["event_id", "event_type", "title", "direction", "severity", "confidence", "event_time", "published_at", "ingested_at", "source_name", "source_tier", "security_ids"]
    for field in required:
        if event.get(field) in (None, "", []):
            errors.append(f"MISSING_{field.upper()}")
    if errors:
        return None, errors

    if event["event_type"] not in cfg["event_type_weights"]:
        errors.append("UNKNOWN_EVENT_TYPE")
    if event["direction"] not in cfg["direction_values"]:
        errors.append("INVALID_DIRECTION")
    if event["source_tier"] not in cfg["source_tiers"]:
        errors.append("INVALID_SOURCE_TIER")
    try:
        severity = int(event["severity"])
        if not cfg["validation"]["minimum_severity"] <= severity <= cfg["validation"]["maximum_severity"]:
            errors.append("INVALID_SEVERITY")
    except (TypeError, ValueError):
        errors.append("INVALID_SEVERITY")
        severity = 0
    try:
        confidence = float(event["confidence"])
        if not cfg["validation"]["minimum_confidence"] <= confidence <= cfg["validation"]["maximum_confidence"]:
            errors.append("INVALID_CONFIDENCE")
    except (TypeError, ValueError):
        errors.append("INVALID_CONFIDENCE")
        confidence = 0.0

    try:
        event_time = parse_ts(event["event_time"], "event_time")
        published_at = parse_ts(event["published_at"], "published_at")
        ingested_at = parse_ts(event["ingested_at"], "ingested_at")
        if cfg["validation"]["reject_ingested_before_published"] and ingested_at < published_at:
            errors.append("INGESTED_BEFORE_PUBLISHED")
        if cfg["validation"]["reject_future_publication_vs_cutoff"] and published_at > cutoff:
            errors.append("PUBLICATION_AFTER_CUTOFF")
        if event_time > published_at + timedelta(days=1):
            errors.append("EVENT_TIME_AFTER_PUBLICATION")
    except ValueError as exc:
        errors.append(str(exc))
        event_time = published_at = ingested_at = cutoff

    security_ids = event.get("security_ids")
    if not isinstance(security_ids, list) or not security_ids or any(not isinstance(x, str) or not x.strip() for x in security_ids):
        errors.append("INVALID_SECURITY_LINKS")

    if event.get("unverified") and confidence > 0.40:
        errors.append("UNVERIFIED_CONFIDENCE_TOO_HIGH")

    if errors:
        return None, sorted(set(errors))

    normalized = dict(event)
    normalized.update({
        "severity": severity,
        "confidence": confidence,
        "security_ids": sorted(set(x.strip() for x in security_ids)),
        "event_time": event_time.isoformat().replace("+00:00", "Z"),
        "published_at": published_at.isoformat().replace("+00:00", "Z"),
        "ingested_at": ingested_at.isoformat().replace("+00:00", "Z"),
    })
    normalized["canonical_fingerprint"] = fingerprint(normalized)
    return normalized, []


def direction_value(direction: str) -> float:
    return {"POSITIVE": 1.0, "NEGATIVE": -1.0, "NEUTRAL": 0.0, "MIXED": 0.0, "UNKNOWN": 0.0}[direction]


def event_signal(event: dict[str, Any], cfg: dict[str, Any], cutoff: datetime) -> float:
    published_at = parse_ts(event["published_at"], "published_at")
    age_days = max(0.0, (cutoff - published_at).total_seconds() / 86400.0)
    half_life = float(cfg["aggregation"]["half_life_days"])
    decay = math.exp(-math.log(2.0) * age_days / half_life) if half_life > 0 else 1.0
    severity_scale = float(event["severity"]) / 5.0
    source_weight = float(cfg["source_tiers"][event["source_tier"]])
    type_weight = float(cfg["event_type_weights"][event["event_type"]])
    return direction_value(event["direction"]) * severity_scale * float(event["confidence"]) * source_weight * type_weight * decay


def context_label(signal: float, events: list[dict[str, Any]], cfg: dict[str, Any]) -> str:
    if not events:
        return "NO_MATERIAL_CONTEXT"
    if any(e.get("data_quality_flags") for e in events):
        return "DATA_REVIEW_REQUIRED"
    positive = any(e["direction"] == "POSITIVE" for e in events)
    negative = any(e["direction"] == "NEGATIVE" for e in events)
    threshold = float(cfg["aggregation"]["context_threshold"])
    if positive and negative and abs(signal) < threshold:
        return "MIXED_CONTEXT"
    if signal >= threshold:
        return "POSITIVE_CONTEXT"
    if signal <= -threshold:
        return "NEGATIVE_CONTEXT"
    return "NO_MATERIAL_CONTEXT"


def summarize_security(security_id: str, events: list[dict[str, Any]], cfg: dict[str, Any], cutoff: datetime) -> dict[str, Any]:
    scored = []
    counts = Counter()
    for event in events:
        sig = event_signal(event, cfg, cutoff)
        enriched = dict(event)
        enriched["event_signal"] = round(sig, 8)
        scored.append(enriched)
        counts[event["direction"]] += 1
    total = sum(x["event_signal"] for x in scored)
    clipped = max(-2.0, min(2.0, total))
    ranked = sorted(scored, key=lambda x: (-x["severity"], -abs(x["event_signal"]), x["published_at"], x["event_id"]))
    highest = ranked[0] if ranked else None
    type_counts = Counter(e["event_type"] for e in events)
    top_types = [k for k, _ in sorted(type_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
    top_n = int(cfg["aggregation"]["top_events_per_security"])
    return {
        "security_id": security_id,
        "research_signal": round(clipped, 8),
        "raw_weighted_signal": round(total, 8),
        "context_label": context_label(clipped, events, cfg),
        "event_counts": {
            "positive": counts["POSITIVE"],
            "negative": counts["NEGATIVE"],
            "neutral": counts["NEUTRAL"] + counts["UNKNOWN"],
            "mixed": counts["MIXED"],
            "total": len(events),
        },
        "highest_severity": highest["severity"] if highest else None,
        "highest_severity_event_id": highest["event_id"] if highest else None,
        "dominant_event_types": top_types,
        "included_event_ids": [x["event_id"] for x in sorted(events, key=lambda e: (e["published_at"], e["event_id"]))],
        "top_events": ranked[:top_n],
    }


def run_research(events_payload: Any, cfg: dict[str, Any], information_cutoff: str) -> dict[str, Any]:
    cutoff = parse_ts(information_cutoff, "information_cutoff")
    events = events_payload.get("events", []) if isinstance(events_payload, dict) else events_payload
    if not isinstance(events, list):
        raise ValueError("EVENTS_MUST_BE_LIST")

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_fp: set[str] = set()
    lookback_start = cutoff - timedelta(days=int(cfg["aggregation"]["lookback_days"]))

    for raw in events:
        if not isinstance(raw, dict):
            rejected.append({"event_id": None, "errors": ["EVENT_NOT_OBJECT"]})
            continue
        normalized, errors = validate_event(raw, cfg, cutoff)
        if errors:
            rejected.append({"event_id": raw.get("event_id"), "errors": errors})
            continue
        assert normalized is not None
        if normalized["event_id"] in seen_ids or normalized["canonical_fingerprint"] in seen_fp:
            duplicates.append({"event_id": normalized["event_id"], "canonical_fingerprint": normalized["canonical_fingerprint"]})
            continue
        seen_ids.add(normalized["event_id"])
        seen_fp.add(normalized["canonical_fingerprint"])
        if parse_ts(normalized["published_at"], "published_at") < lookback_start:
            continue
        accepted.append(normalized)

    by_security: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in accepted:
        for sid in event["security_ids"]:
            by_security[sid].append(event)

    summaries = [summarize_security(sid, evs, cfg, cutoff) for sid, evs in sorted(by_security.items())]
    cfg_hash = cfg.get("configuration_sha256") or canonical_hash({k: v for k, v in cfg.items() if k != "configuration_sha256"})
    output: dict[str, Any] = {
        "engine_version": ENGINE_VERSION,
        "run_status": "INFORMATIONAL_ONLY",
        "information_cutoff": cutoff.isoformat().replace("+00:00", "Z"),
        "lookback_start": lookback_start.isoformat().replace("+00:00", "Z"),
        "configuration_sha256": cfg_hash,
        "non_interference": {
            "scoring_modified": False,
            "portfolio_modified": False,
            "backtest_modified": False,
            "dca_modified": False,
        },
        "counts": {
            "input": len(events),
            "accepted": len(accepted),
            "rejected": len(rejected),
            "duplicates": len(duplicates),
            "security_summaries": len(summaries),
        },
        "accepted_events": sorted(accepted, key=lambda e: (e["published_at"], e["event_id"])),
        "rejected_events": rejected,
        "duplicate_events": duplicates,
        "security_summaries": summaries,
    }
    output["output_sha256"] = canonical_hash(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--information-cutoff", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = run_research(load_json(args.events), load_json(args.config), args.information_cutoff)
    Path(args.output).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
