# Winner Tilt AI — Project Specification v1.3

**Architecture status:** Frozen through Milestone 5  
**Date:** 2026-07-23

## Operating model
Winner Tilt AI is a rules-based long-term US equity selection system. It scores the approved universe monthly, maintains 15 holdings and 15 reserves, directs DCA only to holdings and rebalances in January and July.

## Module status
1. Data Layer — schema frozen; production vendor integrations pending
2. Universe Engine — methodology frozen
3. Scoring Engine — complete and frozen
4. Portfolio Engine — complete and frozen
5. Backtest Engine — production architecture complete and frozen; real performance validation data-gated
6. Research Engine — next
7. Dashboard — pending
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

## Governance
Frozen model rules may not be changed solely to improve historical performance. Production validity is a property of both the engine and the supplied data. Missing data-integrity requirements cannot be waived by configuration.
