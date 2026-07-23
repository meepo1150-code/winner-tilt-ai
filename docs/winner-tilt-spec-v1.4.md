# Winner Tilt AI — Project Specification v1.4

**Architecture status:** Frozen through Milestone 6  
**Date:** 2026-07-23

## Operating model
Winner Tilt AI is a rules-based long-term US equity selection system. It scores the approved universe monthly, maintains 15 holdings and 15 reserves, directs DCA only to holdings, rebalances in January and July, validates the frozen process through point-in-time backtests, and attaches timestamped event intelligence as a non-trading research layer.

## Module status
1. Data Layer — schema frozen; production vendor integrations pending
2. Universe Engine — methodology frozen
3. Scoring Engine — complete and frozen
4. Portfolio Engine — complete and frozen
5. Backtest Engine — production architecture complete and frozen; real performance validation data-gated
6. Research Engine — deterministic architecture complete and frozen; production source integrations pending
7. Dashboard — next
8. Decision Journal — pending integration

## Milestone 5 completion record
- Deterministic walk-forward Backtest Engine v2.0.
- Point-in-time score cutoff and effective-dated membership enforcement.
- Semiannual execution on the first available January/July trading day.
- Transaction ledger, costs, turnover, benchmark and performance analytics.
- Data-manifest gate that fails closed to `VALIDATION_ONLY`.
- Explicit production requirements for PIT fundamentals and estimates, corporate actions, delistings, benchmark history, timestamps and independent look-ahead validation.
- Automated Backtest Engine test suite passing 9/9.
- Synthetic end-to-end run completed but not accepted as investment evidence.

## Milestone 6 completion record
- Deterministic Research Engine v1.0.
- Controlled event registry and relational event schema.
- Mandatory event, publication, ingestion, source, and security-link fields.
- Point-in-time publication cutoff that rejects future information.
- Duplicate detection through canonical event fingerprints.
- Configurable source-tier, event-type, severity, confidence, and time-decay weighting.
- Security research signal constrained to -2 through +2.
- Context labels limited to informational language.
- Explicit non-interference contract preventing research from changing scores, portfolio selections, backtests, or DCA.
- Automated Research Engine test suite passing 10/10.
- Synthetic prototype completed but not accepted as investment evidence.

## Frozen module boundary
The Research Engine may explain events but may not modify:
- raw metric observations;
- category or total scores;
- eligibility or ranking;
- holdings, reserves, weights, exits, turnover, or DCA;
- historical backtest decisions.

## Governance
Frozen model rules may not be changed solely to improve historical performance. Production validity is a property of both the engine and supplied data. Missing data-integrity requirements cannot be waived by configuration. Research events without reliable publication timestamps fail closed.

## Milestone 8 module status — Decision Journal

Status: `DECISION_JOURNAL_AUDIT_LAYER_COMPLETE_PRODUCTION_INTEGRATIONS_PENDING`.

The Decision Journal is a non-interfering audit layer. It records existing run outputs, evidence references, timestamps, validation state, synthetic/prototype labels, non-interference attestations, and immutable hashes. It must not modify frozen scoring, portfolio, backtest, research, or dashboard business logic. Production use remains gated on durable production run identifiers, vendor source snapshots, and approved immutable retention infrastructure.

## Milestone 9 production integration architecture addendum

Status: `PRODUCTION_INTEGRATION_ARCHITECTURE_COMPLETE_LIVE_INTEGRATIONS_PENDING`.

The production architecture is additive and offline: provider interfaces, validation, snapshots, scheduler orchestration, health checks, and structured logging are implemented without changing Milestones 1–8 investment logic. Live vendors, credentials, licensed datasets, production operations, and real investment performance evidence remain pending.
