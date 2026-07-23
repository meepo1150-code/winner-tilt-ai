# Winner Tilt AI — Project Specification v1.1

**Architecture status:** Frozen  
**Universe status:** Frozen  
**Scoring Engine status:** Frozen  
**Date:** 2026-07-23

## Operating model
Winner Tilt AI is a rules-based long-term US equity selection system. It scores the approved universe monthly, maintains 15 holdings and 15 reserves, directs DCA only to current holdings, and rebalances every six months.

## System modules
1. Data Layer
2. Universe Engine
3. Scoring Engine — Milestone 3 complete
4. Portfolio Engine
5. Backtest Engine
6. Research Engine
7. Dashboard
8. Decision Journal

## Locked design decisions
- Hard filters precede scoring.
- Universe and portfolio are separate.
- Universe size is 96: 80 Core and 16 Emerging.
- Monthly ranking does not automatically trigger trading.
- Portfolio rebalance occurs every six months.
- Market regime is a portfolio overlay, not a stock-score component.
- Security identity uses permanent WT_ID values.
- Sector, theme, business stage, quality tier and economic exposure are distinct metadata.
- Quality tier does not affect v1.0 scores.
- Scoring uses immutable versioned configuration and component-level audit records.
- Missing, not-applicable and structurally unsupported metrics are treated separately.
- Rule changes are versioned and must not be made solely to improve historical results.

## Milestone 3 completion record
- Frozen Scoring Engine Specification v1.0.
- Frozen metric registry with 42 metrics.
- Consolidated PostgreSQL schema v1.1.
- Immutable scoring configuration SHA-256 `a5709013e89200e39ee3e2bb3063ff99f55a166467dab5f4ab576d5621a69e4f`.
- Deterministic synthetic validation run covering 96 securities.
- Component, category and flag audit outputs implemented.
- Automated test suite passing.
- Specialized bank, insurer/conglomerate and lender modules explicitly excluded until implemented.

## Next milestone
Milestone 4 designs the Portfolio Engine and Backtest Engine interface: candidate-to-holding conversion, 15+15 construction, concentration limits, six-month rebalance logic, DCA allocation, transaction assumptions, and point-in-time walk-forward testing.
