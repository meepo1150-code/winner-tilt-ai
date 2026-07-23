# Winner Tilt Production Data Integration v1.0

## Purpose

Milestone 9 introduces a deterministic, fail-closed validation layer for production data snapshots. The layer is an ingestion gate only: it validates externally supplied data before downstream engines consume it, and it must not fetch data, score securities, build portfolios, run backtests, or change research context.

## Supported datasets

The integration contract requires three datasets in every run:

- `universe`: active security coverage with `security_id`, `ticker`, `name`, `sector`, and `active`.
- `metrics`: point-in-time metric observations with `security_id`, `metric_id`, `as_of_date`, `value`, `source_name`, `source_tier`, and `ingested_at`.
- `events`: production event references with `event_id`, `event_type`, `security_id`, `published_at`, `source_name`, and `source_tier`.

CSV and JSON row files are supported by the command-line loader. JSON inputs may be a list of row objects or an object containing a `rows` list.

## Validation controls

The validator fails closed by rejecting rows that contain:

- Missing required fields.
- Duplicate natural keys.
- Unknown or inactive linked securities for metrics or events.
- Invalid source tiers.
- Invalid metric values.
- Naive or invalid UTC timestamps.
- Metric `as_of_date`, metric `ingested_at`, or event `published_at` values after the information cutoff.

Rejected rows are reported using dataset name, row number, deterministic row hash, and error codes. Raw vendor row payloads are intentionally omitted from the report.

## Output contract

Every report includes:

- Engine version and run status (`PASS` or `FAIL_CLOSED`).
- Information cutoff normalized to UTC.
- Source file manifest when the CLI is used.
- Accepted/rejected counts by dataset.
- Accepted active security IDs.
- Rejected row summaries.
- Non-interference attestations for scoring, portfolio, backtest, and research engines.
- Deterministic `output_sha256` over the report body.

## Non-interference policy

The production data integration layer is not investment logic. It provides input validation and audit evidence only. A failing integration report must block promotion of a production snapshot until the upstream data issue is corrected or explicitly remediated outside the frozen engines.
