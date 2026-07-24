"""Point-in-time SEC fundamental feature bridge for Winner Tilt AI.

This module is additive: it transforms already-normalized fundamental facts into
long-form metric observations accepted by ``winner_tilt.scoring``. It never
changes scoring, portfolio, or backtest business rules.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

FEATURE_ENGINE_VERSION = "1.0.0"
VALID_OPERATIONS = frozenset({"latest", "growth", "ratio"})
ANNUAL_FORMS = frozenset({"10-K", "10-K/A"})
QUARTERLY_FORMS = frozenset({"10-Q", "10-Q/A"})


class FundamentalFeatureError(ValueError):
    """Raised when feature inputs violate deterministic point-in-time policy."""


@dataclass(frozen=True)
class FeatureDefinition:
    metric_id: str
    operation: str
    numerator_concepts: tuple[str, ...]
    denominator_concepts: tuple[str, ...] = ()
    unit: str | None = None
    forms: tuple[str, ...] = ()
    stale_after_days: int = 550
    scale: float = 1.0

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "FeatureDefinition":
        try:
            definition = cls(
                metric_id=str(raw["metric_id"]),
                operation=str(raw["operation"]),
                numerator_concepts=tuple(str(x) for x in raw["numerator_concepts"]),
                denominator_concepts=tuple(str(x) for x in raw.get("denominator_concepts", ())),
                unit=str(raw["unit"]) if raw.get("unit") is not None else None,
                forms=tuple(str(x) for x in raw.get("forms", ())),
                stale_after_days=int(raw.get("stale_after_days", 550)),
                scale=float(raw.get("scale", 1.0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise FundamentalFeatureError("FUNDAMENTAL_FEATURE_INVALID_DEFINITION") from exc
        definition.validate()
        return definition

    def validate(self) -> None:
        if not self.metric_id or self.operation not in VALID_OPERATIONS or not self.numerator_concepts:
            raise FundamentalFeatureError("FUNDAMENTAL_FEATURE_INVALID_DEFINITION")
        if self.operation == "ratio" and not self.denominator_concepts:
            raise FundamentalFeatureError("FUNDAMENTAL_FEATURE_RATIO_DENOMINATOR_REQUIRED")
        if self.operation != "ratio" and self.denominator_concepts:
            raise FundamentalFeatureError("FUNDAMENTAL_FEATURE_UNEXPECTED_DENOMINATOR")
        if self.stale_after_days < 0 or self.scale == 0:
            raise FundamentalFeatureError("FUNDAMENTAL_FEATURE_INVALID_DEFINITION")


def _parse_utc(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise FundamentalFeatureError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FundamentalFeatureError(code) from exc
    if parsed.tzinfo is None:
        raise FundamentalFeatureError(code)
    return parsed.astimezone(timezone.utc)


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _fact_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Latest publication wins; amendment wins only when timestamps tie."""
    return (
        _parse_utc(row.get("accepted_timestamp"), "FUNDAMENTAL_FEATURE_INVALID_AVAILABLE_AT"),
        str(row.get("report_end", "")),
        bool(row.get("is_amendment", False)),
        str(row.get("accession_number", "")),
        str(row.get("id", "")),
    )


def _eligible_facts(
    facts: Iterable[Mapping[str, Any]],
    definition: FeatureDefinition,
    cutoff: datetime,
    concepts: Sequence[str],
) -> list[Mapping[str, Any]]:
    allowed = set(concepts)
    rows: list[Mapping[str, Any]] = []
    for row in facts:
        available = _parse_utc(row.get("accepted_timestamp"), "FUNDAMENTAL_FEATURE_INVALID_AVAILABLE_AT")
        if available > cutoff:
            continue
        if row.get("concept") not in allowed:
            continue
        if definition.unit is not None and row.get("unit") != definition.unit:
            continue
        if definition.forms and row.get("form") not in definition.forms:
            continue
        value = row.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        rows.append(row)
    return sorted(rows, key=_fact_sort_key)


def _latest(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    return rows[-1] if rows else None


def _period_family(form: Any) -> str:
    if form in ANNUAL_FORMS:
        return "annual"
    if form in QUARTERLY_FORMS:
        return "quarterly"
    return str(form or "unknown")


def _growth(rows: Sequence[Mapping[str, Any]]) -> tuple[float, tuple[Mapping[str, Any], ...]] | None:
    current = _latest(rows)
    if current is None:
        return None
    family = _period_family(current.get("form"))
    candidates = [
        row for row in rows
        if row.get("report_end") < current.get("report_end")
        and _period_family(row.get("form")) == family
        and row.get("fiscal_period") == current.get("fiscal_period")
    ]
    prior = _latest(candidates)
    if prior is None:
        return None
    prior_value = float(prior["value"])
    if prior_value == 0:
        raise FundamentalFeatureError("FUNDAMENTAL_FEATURE_ZERO_GROWTH_BASE")
    return float(current["value"]) / prior_value - 1.0, (current, prior)


def _ratio(
    numerators: Sequence[Mapping[str, Any]], denominators: Sequence[Mapping[str, Any]]
) -> tuple[float, tuple[Mapping[str, Any], ...]] | None:
    numerator = _latest(numerators)
    if numerator is None:
        return None
    same_period = [row for row in denominators if row.get("report_end") == numerator.get("report_end")]
    denominator = _latest(same_period)
    if denominator is None:
        return None
    denominator_value = float(denominator["value"])
    if denominator_value == 0:
        raise FundamentalFeatureError("FUNDAMENTAL_FEATURE_ZERO_RATIO_DENOMINATOR")
    return float(numerator["value"]) / denominator_value, (numerator, denominator)


def _observation(
    security_id: str,
    definition: FeatureDefinition,
    cutoff: datetime,
    peer_group: str,
    selected: tuple[Mapping[str, Any], ...] | None,
    value: float | None,
) -> dict[str, Any]:
    if not selected:
        return {
            "security_id": security_id,
            "metric_id": definition.metric_id,
            "value": None,
            "missing_data_class": "TEMPORARILY_UNAVAILABLE",
            "peer_group": peer_group,
            "stale_critical": False,
            "available_at": None,
            "report_end": None,
            "source_fact_ids": [],
            "source_accessions": [],
        }
    available = max(_parse_utc(row["accepted_timestamp"], "FUNDAMENTAL_FEATURE_INVALID_AVAILABLE_AT") for row in selected)
    report_end = max(str(row["report_end"]) for row in selected)
    age_days = (cutoff.date() - datetime.fromisoformat(report_end).date()).days
    return {
        "security_id": security_id,
        "metric_id": definition.metric_id,
        "value": value * definition.scale if value is not None else None,
        "missing_data_class": "VALID",
        "peer_group": peer_group,
        "stale_critical": age_days > definition.stale_after_days,
        "available_at": available.isoformat().replace("+00:00", "Z"),
        "report_end": report_end,
        "source_fact_ids": sorted(str(row["id"]) for row in selected),
        "source_accessions": sorted({str(row["accession_number"]) for row in selected}),
    }


def build_fundamental_observations(
    facts: Iterable[Mapping[str, Any]],
    definitions: Iterable[FeatureDefinition | Mapping[str, Any]],
    *,
    information_cutoff: str,
    peer_groups: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build deterministic scoring observations using only facts known at cutoff."""
    cutoff = _parse_utc(information_cutoff, "FUNDAMENTAL_FEATURE_INVALID_CUTOFF")
    parsed = tuple(d if isinstance(d, FeatureDefinition) else FeatureDefinition.from_mapping(d) for d in definitions)
    metric_ids = [d.metric_id for d in parsed]
    if len(set(metric_ids)) != len(metric_ids):
        raise FundamentalFeatureError("FUNDAMENTAL_FEATURE_DUPLICATE_METRIC_ID")

    rows = [dict(row) for row in facts]
    by_security: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        security_id = row.get("security_id")
        if not isinstance(security_id, str) or not security_id:
            raise FundamentalFeatureError("FUNDAMENTAL_FEATURE_SECURITY_ID_REQUIRED")
        by_security.setdefault(security_id, []).append(row)

    observations: list[dict[str, Any]] = []
    for security_id in sorted(by_security):
        security_facts = by_security[security_id]
        peer_group = (peer_groups or {}).get(security_id, "")
        for definition in parsed:
            numerator_rows = _eligible_facts(
                security_facts, definition, cutoff, definition.numerator_concepts
            )
            value: float | None = None
            selected: tuple[Mapping[str, Any], ...] | None = None
            if definition.operation == "latest":
                current = _latest(numerator_rows)
                if current is not None:
                    value, selected = float(current["value"]), (current,)
            elif definition.operation == "growth":
                result = _growth(numerator_rows)
                if result is not None:
                    value, selected = result
            else:
                denominator_rows = _eligible_facts(
                    security_facts, definition, cutoff, definition.denominator_concepts
                )
                result = _ratio(numerator_rows, denominator_rows)
                if result is not None:
                    value, selected = result
            observations.append(
                _observation(security_id, definition, cutoff, peer_group, selected, value)
            )

    payload = {
        "engine_version": FEATURE_ENGINE_VERSION,
        "information_cutoff": cutoff.isoformat().replace("+00:00", "Z"),
        "definitions_sha256": _canonical_hash([d.__dict__ for d in parsed]),
        "source_facts_sha256": _canonical_hash(rows),
        "observations": observations,
        "point_in_time_policy": "accepted_timestamp_lte_information_cutoff",
        "downstream_contract": "winner_tilt.scoring_long_form_observations",
    }
    payload["output_sha256"] = _canonical_hash(payload)
    return payload


def write_scoring_observations(payload: Mapping[str, Any], path: str | Path) -> None:
    """Write the exact CSV columns consumed by the frozen scoring engine."""
    fields = ("security_id", "metric_id", "value", "missing_data_class", "peer_group", "stale_critical")
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in payload.get("observations", ()):
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def score_vintage_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return metadata that a scoring result must carry into backtest vintages."""
    cutoff = payload.get("information_cutoff")
    return {
        "information_cutoff": cutoff,
        "generated_at": cutoff,
        "fundamental_feature_output_sha256": payload.get("output_sha256"),
        "available_at_policy": "each_score_row_must_not_exceed_information_cutoff",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--facts", required=True)
    parser.add_argument("--definitions", required=True)
    parser.add_argument("--information-cutoff", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--scoring-csv")
    args = parser.parse_args()
    facts_payload = json.loads(Path(args.facts).read_text(encoding="utf-8"))
    definitions_payload = json.loads(Path(args.definitions).read_text(encoding="utf-8"))
    facts = facts_payload.get("rows", facts_payload)
    definitions = definitions_payload.get("features", definitions_payload)
    result = build_fundamental_observations(
        facts, definitions, information_cutoff=args.information_cutoff
    )
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.scoring_csv:
        write_scoring_observations(result, args.scoring_csv)


if __name__ == "__main__":
    main()
