# Winner Tilt AI — Milestone 11 SEC EDGAR Live Pilot Runbook v1.0

## Status

Operational infrastructure only. Live mode is disabled unless all required runtime variables are explicitly supplied. Downstream consumption is prohibited.

## Required runtime variables

- `WINNER_TILT_SEC_EDGAR_LIVE_ENABLED=true`
- `WINNER_TILT_SEC_EDGAR_USER_AGENT=<application-name contact-channel>`
- `WINNER_TILT_SEC_EDGAR_CIKS=<comma-separated approved CIKs>`

Optional bounded settings:

- `WINNER_TILT_SEC_EDGAR_TIMEOUT_SECONDS` — default `10`, maximum `30`
- `WINNER_TILT_SEC_EDGAR_MAX_ATTEMPTS` — default `3`, maximum `3`
- `WINNER_TILT_SEC_EDGAR_BACKOFF_SECONDS` — default `0.5`, maximum `5`
- `WINNER_TILT_SEC_EDGAR_MAX_RPS` — default `2`, maximum `2`
- `WINNER_TILT_SEC_EDGAR_MAX_TOTAL_REQUESTS` — default `3`, maximum `3`
- `WINNER_TILT_SEC_EDGAR_KILL_SWITCH=true` — blocks an enabled run without a code change

Do not commit a real contact identity. Supply it only in the authorized runtime environment.

## Command

```bash
python -m winner_tilt.sec_edgar_pilot --snapshot-dir <isolated-output-directory>
```

## Pre-run checklist

1. Confirm the approved CIK allowlist contains no more than three entries.
2. Confirm the runtime User-Agent contains an application name and monitored contact channel.
3. Confirm the snapshot directory is isolated from all scoring, portfolio, backtest, research, DCA, exit, journal-decision, and dashboard input paths.
4. Confirm raw payload retention remains disabled.
5. Confirm the kill switch is available to the operator.
6. Confirm the current branch or release has passing CI.

## Stop conditions

Stop immediately on:

- HTTP 403 or 429
- malformed or non-object JSON
- unsupported or ambiguous timestamp semantics
- future acceptance timestamps
- duplicate natural keys
- nondeterministic replay
- unexpected downstream reachability
- request ceiling or rate-limit policy violations

Set `WINNER_TILT_SEC_EDGAR_KILL_SWITCH=true` before any retry after a stop condition.

## Output contract

Each successful run creates immutable canonical JSON files under a UTC run-id directory. Every snapshot must contain:

- provider and vendor identity
- acquisition, effective, and publication timestamps
- normalized rows
- source reference
- raw content SHA-256
- `raw_payload_retained: false`
- `pilot_tag: ingest_only_no_downstream_consumption`

Existing files are never overwritten.

## Post-run evidence

Record separately:

- run start and end time
- approved operator and authorization reference
- CIK count and request count
- success/failure by CIK
- freshness and validation result
- snapshot paths and hashes
- any retry/backoff activity
- stop-condition assessment
- rollback action
- final go/no-go recommendation

## Rollback

1. Activate the runtime kill switch.
2. Disable live mode.
3. Quarantine the isolated run directory.
4. Do not delete snapshots required for audit unless retention policy explicitly requires it.
5. Verify no pilot path is referenced by downstream engines.
6. Record the reason and corrective action before a new authorization.
