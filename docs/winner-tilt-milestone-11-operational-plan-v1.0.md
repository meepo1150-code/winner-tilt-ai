# Winner Tilt AI — Milestone 11 Operational Live-Ingest Plan

Status: `MILESTONE_11_INFRASTRUCTURE_IMPLEMENTATION_AUTHORIZED_LIVE_RUN_BLOCKED_PENDING_RUNTIME_IDENTITY`

Issue: #13

Base: `main` at `398d1899bebdba16d26d1215c698d2798199d3e2`

Branch: `milestone-11/sec-edgar-live-pilot`

## 1. Objective

Implement and validate the operational infrastructure required for one tightly bounded SEC EDGAR Company Facts live-ingest pilot. The milestone must stop before any live pilot snapshot can influence scoring, portfolio construction, backtesting, research ranking, DCA, exits, the decision journal, or dashboard decision paths.

## 2. Authorization boundary

Authorized now:

- concrete HTTPS transport behind the existing SEC adapter contract
- runtime configuration loading and fail-closed validation
- request throttling, timeout, retry, backoff, circuit-breaker, and kill-switch controls
- explicit pilot command/entry point
- deterministic mock/fixture tests
- immutable ingest-only snapshots and operational reports

Not authorized now:

- committing a real contact email or identity
- enabling live mode by default
- unattended scheduled live acquisition
- raw-response retention
- full-universe acquisition
- downstream engine consumption
- any change to frozen investment logic

## 3. Initial pilot universe

Maximum initial allowlist size: 2 CIKs.

The concrete CIKs must be supplied through an approved runtime configuration. Repository defaults contain no live allowlist and therefore cannot perform a live call.

Rules:

- every CIK must be a 10-digit normalized identifier
- duplicate CIKs fail closed
- the command must reject any CIK outside the runtime allowlist
- request count must not exceed the number of approved CIKs

## 4. Runtime identity

SEC live mode requires a declared User-Agent supplied at runtime.

Required environment variables:

- `WINNER_TILT_SEC_LIVE_ENABLED=true`
- `WINNER_TILT_SEC_USER_AGENT=<application identity and contact>`
- `WINNER_TILT_SEC_ALLOWED_CIKS=<comma-separated allowlist>`

The application must not log the full User-Agent. Logs may record only that a non-empty identity was supplied and a non-reversible fingerprint.

No real contact identity is stored in repository files, fixtures, reports, snapshots, or CI configuration.

## 5. Network policy

- base host fixed to `data.sec.gov`
- HTTPS only
- redirect target must remain on the approved host
- maximum 2 requests per second
- default timeout: 10 seconds
- maximum attempts per CIK: 3
- retryable: timeout, connection error, HTTP 429, and HTTP 5xx
- non-retryable: HTTP 400, 401, 403, 404, invalid host, invalid content type, malformed JSON, or policy violation
- exponential backoff with deterministic injectable sleep/clock
- maximum total requests per run: 6 for the two-CIK pilot
- circuit breaker opens after 2 consecutive access-policy responses (`403` or `429`)

## 6. Kill switch

Live execution requires both:

1. repository configuration leaves the provider disabled by default; and
2. runtime `WINNER_TILT_SEC_LIVE_ENABLED` is exactly `true`.

Removing or changing the runtime flag disables live acquisition without a code change.

Any circuit-breaker trip, validation failure, or snapshot integrity failure stops the remaining run.

## 7. Raw payload policy

Raw payload retention remains disabled.

Permitted audit data:

- canonical raw-content SHA-256
- source reference
- acquisition timestamp
- filing acceptance timestamp
- accession number
- normalized rows
- normalized snapshot hash
- validation result and rejection reasons

The raw JSON response must not be written to disk by the pilot command.

## 8. Snapshot isolation

All live pilot snapshots must carry:

`pilot_scope = ingest_only_no_downstream_consumption`

They must be written to a dedicated pilot output location and excluded from all existing engine input discovery.

The pilot command must not import or invoke scoring, portfolio, backtest, research, DCA, exit, decision-journal decision, or dashboard modules.

## 9. Required operational reports

Each run produces metadata-only reports for:

- acquisition attempts and final status
- validation results
- freshness and timestamp ordering
- provenance completeness
- row and concept counts
- snapshot identifiers and hashes
- retry/backoff events
- circuit-breaker state
- quarantine and rollback outcome
- explicit confirmation that downstream consumption was not attempted

Reports must not include the runtime User-Agent or raw payload.

## 10. Test requirements

- live mode absent or false makes zero network calls
- missing User-Agent fails before network access
- empty or oversized allowlist fails before network access
- unapproved host and redirects fail closed
- rate limiter is deterministic under injected clock/sleep
- retry/backoff is deterministic
- repeated 403/429 opens the circuit breaker
- malformed JSON and unsupported content type fail closed
- request ceiling cannot be exceeded
- raw payload is never persisted
- snapshots are deterministic across fixture replay
- operational reports redact runtime identity
- frozen-engine tests remain unchanged and pass

## 11. Live-run gate

Infrastructure and tests may be merged while live mode remains disabled.

A real network run may occur only after the repository owner supplies an appropriate runtime User-Agent outside the repository and explicitly authorizes the concrete CIK allowlist.

## 12. Completion definition

Milestone 11 infrastructure is complete when:

- transport, runtime config, command, snapshots, reports, and tests pass CI
- repository defaults remain live-disabled
- no real identity or raw payload is committed
- a readiness report records whether the system is technically ready for a separately authorized live run

A successful infrastructure merge does not authorize downstream consumption.