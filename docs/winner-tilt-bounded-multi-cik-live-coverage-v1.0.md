# Winner Tilt AI — Bounded Multi-CIK Live Coverage v1.0

## Purpose

Milestone 18 expands the completed single-CIK live SEC pilot into a manually authorized, bounded multi-security research run. It does not change scoring, portfolio, backtest, or execution rules.

## Authorization

The workflow accepts a comma-separated CIK list and requires the exact phrase:

`AUTHORIZE_MULTI_CIK_SEC_SHADOW_RESEARCH_ONLY`

Only active one-to-one mappings in `config/winner-tilt-security-identifiers-v1.0.0.csv` are accepted. Tickers and company names are never used to infer CIKs.

## Boundaries

- maximum 3 CIKs and 3 live SEC requests per run
- manual `workflow_dispatch` only
- recursive immutable snapshot discovery
- exactly one snapshot per approved CIK
- no extra, missing, or duplicate snapshots
- canonical universe path: `database/universe-v1.0.csv`
- aggregate snapshot and per-source SHA-256 manifest
- existing point-in-time scoring and shadow portfolio contracts
- insufficient coverage remains research-only and does not relax 15 holdings + 15 reserves
- broker connection, orders, automatic DCA, and automatic exits remain disabled

## Artifacts

- `authorization-gate.json`
- `source-snapshots/CIK*.json`
- `sec-companyfacts-aggregate-snapshot.json`
- `sec-companyfacts-aggregate-manifest.json`
- `certified-score-vintage.json`
- `certified-shadow-portfolio.json`
- `decision-journal-record.json`
- `dashboard-shadow-view.json`
- `run-manifest.json`
- `authorized-multi-cik-run-manifest.json`

## Milestone 17 regression gates reused

1. Snapshot discovery is recursive rather than `maxdepth 1`.
2. The canonical universe path is `database/universe-v1.0.csv`.
3. M13 named-hash lineage remains accepted by M14.
4. Insufficient security coverage completes only as non-executable research.
5. Every final artifact bundle rechecks the execution boundary and hash lineage.

## Completion gate

Repository CI must pass, followed by one manually authorized live run using 1–3 registered CIKs. Issue #34 remains open until the live artifact bundle succeeds.
