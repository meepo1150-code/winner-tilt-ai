# Milestone 22 — Factor Attribution and Explainability Certification

Milestone 22 adds a deterministic research-only certification layer that explains certified scores without modifying the scoring, portfolio, replay, backtest, or performance engines.

## Certified outputs

- per-security factor contributions reconciled exactly to total score
- positive drivers, negative drivers, penalties, and eligibility explanation
- aggregate attribution by factor, security, sector, and replay period
- lineage hashes for score inputs, historical replay, and performance certification
- execution-boundary enforcement and fail-closed diagnostics

## Status

Successful certification emits `FACTOR_ATTRIBUTION_CERTIFIED_RESEARCH_ONLY`. Historical periods with insufficient coverage remain explicitly research-only and do not become production-ready through attribution.

## Manual completion gate

Run **Factor Attribution Certification** on `main` with authorization `AUTHORIZE_FACTOR_ATTRIBUTION_RESEARCH_ONLY`. The workflow emits an attribution report, explainability report, manifest, source fixtures, and diagnostic log in one immutable artifact.

## Safety

Broker connectivity, order creation, order execution, automatic DCA, and automatic exits remain disabled.
