# Winner Tilt AI — Project Specification v1.2

**Architecture status:** Frozen through Milestone 4  
**Universe status:** Frozen  
**Scoring Engine status:** Frozen  
**Portfolio Engine status:** Frozen  
**Backtest interface status:** Frozen; production engine deferred  
**Date:** 2026-07-23

## Operating model
Winner Tilt AI is a rules-based long-term US equity selection system. It scores the approved universe monthly, maintains 15 holdings and 15 reserves, directs DCA only to current holdings, and rebalances every six months.

## System modules
1. Data Layer
2. Universe Engine
3. Scoring Engine — Milestone 3 complete
4. Portfolio Engine — Milestone 4 complete
5. Backtest Engine — interface/prototype complete; production point-in-time implementation is Milestone 5
6. Research Engine
7. Dashboard
8. Decision Journal

## Locked design decisions
- Hard filters precede scoring.
- Universe and portfolio are separate.
- Universe size is 96: 80 Core and 16 Emerging.
- Monthly ranking does not automatically trigger trading.
- Portfolio rebalance occurs every six months, scheduled for January and July.
- Portfolio consists of 15 holdings and 15 reserves.
- DCA allocation is restricted to current holdings.
- Market regime is a portfolio overlay, not a stock-score component.
- Security identity uses permanent WT_ID values.
- Sector, theme, business stage, quality tier and economic exposure are distinct metadata.
- Portfolio construction controls Universe Group, Primary Theme, Economic Exposure, Business Stage and Emerging exposure.
- Existing holdings may remain inside the versioned rank/score buffer.
- One-way turnover is capped at 40% per scheduled rebalance unless a future version defines mandatory-event exceptions.
- Default position sizing is equal weight, with an 8% single-position ceiling.
- Scoring and portfolio configuration are immutable and hash-identified.
- Rule changes are versioned and must not be made solely to improve historical results.

## Milestone 4 completion record
- Frozen Portfolio Policy v1.0.
- Frozen portfolio configuration v1.0.0 with SHA-256.
- Deterministic Portfolio Engine v1.0.
- 15+15 construction, concentration controls, buffer, turnover control and DCA allocation implemented.
- BUY/HOLD/EXIT/WATCH decision audit implemented.
- Backtest Engine Interface v1.0 frozen.
- Fixed-portfolio prototype valuation engine implemented and labelled `PROTOTYPE_ONLY`.
- Portfolio/backtest PostgreSQL schema v1.0 added.
- Automated Portfolio Engine test suite passing 12/12.
- Synthetic prototype portfolio generated from the Milestone 3 synthetic score run.

## Next milestone
Milestone 5 builds and validates the production point-in-time walk-forward Backtest Engine, including historical universe membership, delisted securities, corporate actions, score vintages, benchmark integration, transaction ledger and anti-look-ahead tests.
