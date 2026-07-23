# Winner Tilt AI — Research Engine Policy v1.0

**Milestone:** 6 — Research Engine (Event Intelligence)  
**Status:** Frozen  
**Date:** 2026-07-23

## Purpose
The Research Engine converts timestamped external events into auditable security-level research context. It explains developments around portfolio and watchlist names without changing the frozen Scoring Engine, Portfolio Engine, or Backtest Engine.

## Non-interference rule
Research outputs are informational overlays only. They may be displayed in the Dashboard or written to the Decision Journal, but they may not:
- modify a metric observation;
- modify a category score or total score;
- change eligibility, rank, portfolio selection, weight, turnover, or DCA allocation;
- create a historical portfolio decision that was not produced by the frozen engines.

## Point-in-time contract
Every accepted event must contain:
- stable `event_id`;
- `event_type` from the controlled registry;
- `event_time` describing when the underlying event occurred;
- `published_at` describing when the information became public;
- `ingested_at` describing when Winner Tilt received it;
- source name and source URL or source reference;
- at least one linked `security_id`;
- direction, severity, and confidence.

A research snapshot with an `information_cutoff` may include only events whose `published_at` is at or before that cutoff. Missing or malformed publication timestamps fail closed.

## Classification scales
### Direction
`POSITIVE`, `NEGATIVE`, `NEUTRAL`, `MIXED`, `UNKNOWN`

### Severity
Integer 1–5:
1. routine or low consequence
2. limited consequence
3. material
4. highly material
5. potentially thesis-changing

### Confidence
Decimal 0–1. Confidence measures classification confidence, not investment certainty.

### Research signal
A separate explanatory signal from -2 to +2:
- `-2`: strong negative context
- `-1`: negative context
- `0`: neutral, mixed, or insufficient context
- `+1`: positive context
- `+2`: strong positive context

The signal is derived deterministically from direction, severity, confidence, and event-type weight. It is not a stock score and cannot be consumed by portfolio construction.

## Event lifecycle and deduplication
Events are immutable after acceptance. Corrections create a new event version linked by `supersedes_event_id`. Duplicate candidates are detected by a canonical fingerprint of source, external ID, event type, publication timestamp, title, and linked securities.

## Aggregation
Security summaries use a configurable lookback window and time decay. Aggregation must expose:
- included event IDs;
- positive, negative, neutral, and mixed counts;
- weighted research signal;
- highest-severity event;
- dominant event types;
- data-quality flags.

No output may be labelled `BUY`, `SELL`, or a price target. Watchlist language is limited to `POSITIVE_CONTEXT`, `NEGATIVE_CONTEXT`, `MIXED_CONTEXT`, `NO_MATERIAL_CONTEXT`, or `DATA_REVIEW_REQUIRED`.

## Data-source governance
Accepted sources must be identified in configuration. Primary issuer, regulator, exchange, and government sources should take priority over secondary reporting. Analyst revisions must retain provider timestamp and snapshot date. Rumours must be classified as unverified and cannot exceed confidence 0.40 unless independently confirmed.

## Audit output
Every run records engine version, configuration hash, information cutoff, source hashes when supplied, accepted/rejected counts, duplicate counts, event-level validation results, security summaries, and deterministic output hash.

## Frozen v1.0 limitations
- No NLP or LLM classification is required for deterministic operation.
- No sentiment inference from raw article text.
- No automatic source crawling.
- No impact on model scores or portfolio decisions.
- No historical research validation without timestamp-complete event archives.
