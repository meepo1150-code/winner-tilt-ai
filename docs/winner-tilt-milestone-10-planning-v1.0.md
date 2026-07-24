# Winner Tilt AI — Milestone 10 Planning and Readiness Gates

Status: `PLAN_REVIEW_REQUIRED_IMPLEMENTATION_BLOCKED`

Issue: #10

Planning branch: `milestone-10/live-data-pilot-planning`

Base: `main` at Milestone 9 merge commit `15b9b828c9c956c674c68523532007ccf7a14d94`

## 1. Objective

Prepare a controlled, reversible, read-only live-data pilot without changing or enabling any downstream investment logic.

Milestone 10 implementation remains blocked until this plan is explicitly approved.

## 2. Recommended pilot

### Provider

U.S. Securities and Exchange Commission (SEC) EDGAR data APIs.

### Dataset class

Company Facts XBRL fundamentals for a deliberately small allowlisted security set.

### Initial endpoint class

`data.sec.gov/api/xbrl/companyfacts/CIK##########.json`

### Why this pilot is recommended

- Official first-party regulatory source.
- No API key or paid subscription is required.
- Filing, period, form, accession, and fact metadata support provenance and point-in-time validation.
- The dataset maps naturally to the existing fundamentals provider contract.
- A small allowlist makes cost, load, schema variance, and rollback manageable.
- It tests real network acquisition while keeping market-price and portfolio execution risks out of scope.

### Limitations

- It is not a real-time market-data source.
- XBRL concepts vary by issuer and filing history.
- Restatements, amended filings, units, frames, fiscal calendars, and duplicate facts require explicit rules.
- SEC fair-access limits and declared user-agent requirements must be enforced.
- Public availability does not remove the need to document retention, attribution, and operational policy.

## 3. Mandatory operating constraints

- Read-only acquisition only.
- No live data may flow into scoring, portfolio construction, backtesting, research ranking, DCA, exits, or dashboard decisions.
- No credentials, email addresses, secrets, or environment-specific identifiers may be committed.
- Network access must be dependency-injected and disabled by default in tests.
- Tests must use recorded or synthetic fixtures, not uncontrolled live calls.
- The adapter must fail closed on malformed, stale, future-dated, incomplete, untraceable, or policy-noncompliant results.
- SEC request rate must remain materially below the published maximum of 10 requests per second; the pilot target is no more than 2 requests per second with exponential backoff.
- Requests must send a declared user agent supplied through runtime configuration.

## 4. Metadata normalization proposal

### Canonical status source

The active project manifest is the machine-readable canonical source for repository status. README, specifications, structure documents, and reports are human-readable projections and must reference the canonical manifest rather than independently redefine status.

### Manifest naming

Create a new active manifest whose filename matches its embedded version, for example:

`config/winner-tilt-project-manifest-v1.9.json`

Do not rename the current manifest in place. Archive the current active file only after all references and hashes are intentionally updated.

### Lineage rules

- `manifest_version` must match the filename version.
- `previous_manifest` must point to the immediately preceding immutable manifest file.
- The active manifest must not list itself as its previous manifest.
- Archived manifests remain immutable.
- Self-hash exclusion must remain explicit.
- Milestone status must use one controlled value and one definition.

### Proposed Milestone 10 planning status

`MILESTONE_10_PLAN_APPROVED_IMPLEMENTATION_NOT_STARTED`

This status may be applied only after plan approval. Until then, retain:

`PLAN_REVIEW_REQUIRED_IMPLEMENTATION_BLOCKED`

## 5. Provider contract mapping to define before code

The implementation design must document mappings for:

- provider identity: `sec_edgar`
- provider contract version
- retrieval timestamp in UTC
- filing acceptance timestamp where available
- report period/end date
- filing form
- accession number
- CIK and security registry link
- taxonomy namespace and concept
- unit
- raw value and normalized value
- source URL/reference without sensitive query material
- validation state and rejection reasons
- raw-response content hash
- normalized-snapshot content hash

No adapter code should be written until this mapping is reviewed.

## 6. Point-in-time and duplicate rules to approve

- A fact is not available before the filing acceptance timestamp.
- Amended filings must not silently overwrite earlier records.
- Restatements must preserve prior versions and lineage.
- Duplicate natural keys must be rejected or resolved by a documented deterministic precedence rule.
- Unit conversion is prohibited unless an approved deterministic conversion rule exists.
- Fiscal period labels must not be assumed to align with calendar quarters.
- Missing acceptance timestamps, accession numbers, units, or source references must fail closed for the pilot.

## 7. Security and configuration design

- Runtime user-agent identity must come from environment configuration.
- Logs must redact contact data and environment details.
- Network timeouts, retries, backoff, request ceiling, and circuit-breaker behavior must be configurable.
- The adapter must support an offline mode.
- Raw payload retention must be configurable and default to disabled until retention policy is approved.
- No provider response may contain executable content that is interpreted by the application.

## 8. Proposed acceptance tests

### Contract

- Valid Company Facts fixture maps deterministically to the provider contract.
- Unknown fields do not alter normalized output unless explicitly supported.
- Contract version mismatch fails closed.

### Provenance and time

- Missing accession number fails.
- Missing or invalid filing timestamp fails.
- Future-dated filing acceptance fails.
- Fact availability respects the information cutoff.
- Raw and normalized hashes are stable across replay.

### Data quality

- Unsupported units fail or quarantine.
- Conflicting duplicate facts follow an approved deterministic policy.
- Amended filings preserve lineage.
- Unknown CIK/security links fail.
- Empty or truncated responses fail.

### Operations

- HTTP 403, 404, 429, 500, timeout, invalid JSON, and connection failure are handled without partial success.
- Rate limiting and exponential backoff are deterministic under injected clocks/transports.
- User-agent configuration is required for live mode.
- Logs contain no secrets or contact identifiers.
- Offline tests make zero network calls.

### Non-interference

- Existing scoring, portfolio, backtest, research, DCA, exit, journal, and dashboard behavior remains unchanged.
- Existing frozen-engine tests remain unchanged and pass.
- Live pilot snapshots are stored separately and are not selected by downstream engines.

## 9. Rollback and kill conditions

Immediately disable the pilot if any of the following occurs:

- SEC policy or access requirements cannot be satisfied.
- Repeated 403 or 429 responses indicate access-policy problems.
- Timestamp semantics cannot be mapped without ambiguity.
- Raw data cannot be retained or discarded consistently with policy.
- Security registry links are unreliable.
- Normalization requires changes to frozen investment logic.
- Live data becomes reachable by downstream decision engines without a separate approval.
- Audit hashes or replay outputs are nondeterministic.

Rollback consists of disabling the provider in configuration, preserving audit metadata, quarantining pilot snapshots, and reverting the adapter-only change set without modifying frozen engines.

## 10. Review decisions required

Reviewers must explicitly approve or reject:

1. SEC EDGAR Company Facts as the first provider/dataset pilot.
2. Small allowlisted universe rather than full-universe acquisition.
3. Maximum pilot request rate of 2 requests per second.
4. Required runtime user-agent configuration.
5. No raw-payload retention until policy approval.
6. Canonical manifest and lineage normalization approach.
7. Point-in-time, amendment, duplicate, and unit rules.
8. Acceptance tests and rollback conditions.

## 11. Work sequence after approval

1. Normalize project metadata and manifest lineage in a documentation/config-only change.
2. Add provider-specific mapping specification and fixture schema.
3. Implement an isolated SEC EDGAR adapter behind the existing provider interface.
4. Add deterministic replay, failure-mode, security, and non-interference tests.
5. Run an explicitly authorized small-universe ingest-only pilot.
6. Produce readiness, provenance, freshness, reconciliation, and rollback reports.
7. Stop at a second approval gate before any downstream consumption.

## 12. Current boundary

This document is planning output only. No production adapter, network client, engine integration, live provider activation, credential handling, or downstream consumption is authorized by this commit.
