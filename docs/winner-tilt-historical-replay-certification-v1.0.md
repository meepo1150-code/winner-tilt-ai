# Winner Tilt AI Historical Replay Certification v1.0

## Purpose

Milestone 20 certifies an ordered series of point-in-time score vintages for historical replay and walk-forward research. It does not replace the Backtest Engine. It validates the inputs and period-level readiness before performance analytics are added in a later milestone.

## Period outcomes

- `PORTFOLIO_READY`: eligible candidates meet the frozen holdings plus reserves requirement.
- `INSUFFICIENT_COVERAGE`: the certified vintage is valid but does not contain enough eligible candidates.
- `BLOCKED`: authorization, timestamp, certification, uniqueness, or schema validation failed.

Insufficient coverage is a research result. It does not relax portfolio rules and does not fabricate holdings.

## Point-in-time controls

Every vintage must have one certified payload, one unique information cutoff, a generation timestamp at or after that cutoff, and no result whose `available_at` exceeds the cutoff. Vintage files are discovered recursively and sorted by cutoff.

## Regression contracts retained

- recursive discovery instead of top-level-only lookup
- canonical repository path `database/universe-v1.0.csv`
- safe authorization choice input
- persistent diagnostics on failure
- fail-closed duplicate cutoff and lookahead checks
- research-only execution boundary
- deterministic canonical and file SHA-256 lineage

## Outputs

The workflow emits:

- ordered certified vintage fixtures or supplied replay vintages
- `historical-replay-manifest.json`
- `historical-replay-output.log`

The manifest includes per-period status, coverage, shortfall, source file hashes, aggregate lineage, and an execution boundary with all execution flags disabled.

## Safety

Milestone 20 does not connect to a broker, create or execute orders, automate DCA or exits, or modify scoring, portfolio, or backtest rules.
