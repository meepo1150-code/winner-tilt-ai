# Winner Tilt AI — Portfolio Policy v1.0

**Status:** Frozen  
**Freeze date:** 2026-07-23  
**Milestone:** 4

## Purpose
Convert the frozen monthly Scoring Engine ranking into an auditable 15-holding portfolio and 15-name reserve list. The Portfolio Engine does not alter scores and does not use market timing.

## Operating cadence
- Scores are refreshed monthly.
- Monthly rank changes update monitoring and reserve status only.
- Trading occurs at scheduled six-month reviews in January and July, except mandatory corporate-action or hard-filter events.
- DCA is directed only to current holdings using portfolio weights.

## Construction order
1. Remove ineligible score results.
2. Sort by overall rank and permanent WT_ID tie-break.
3. Retain existing holdings inside the rank/score buffer when constraints permit.
4. Fill 15 holdings using the highest-ranked candidates that satisfy concentration limits.
5. Apply the one-way turnover ceiling.
6. Fill 15 reserves from remaining candidates using the same diversification logic.
7. Assign weights and produce BUY, HOLD, EXIT and WATCH decisions.

## Frozen v1.0 limits
- Holdings: 15
- Reserves: 15
- Maximum Emerging holdings: 3
- Maximum per Universe Group: 4
- Maximum per Primary Theme: 3
- Maximum per exact Economic Exposure bucket: 3
- Maximum per Business Stage: 10
- Holding buffer: rank 20 and no more than 5 score points below the rank-15 cutoff
- Maximum one-way turnover per scheduled rebalance: 40% (6 of 15 holdings)
- Default sizing: equal weight
- Maximum position weight: 8%

## Weighting modes
The implementation supports equal weight, score weighted and risk adjusted. Equal weight is the frozen default. Alternative modes require a new versioned configuration; they may not be selected merely because a historical backtest looks better.

## Economic exposure limitation
Universe v1.0 stores an auditable text phrase in `Economic_Exposure`. Portfolio Engine v1.0 treats each exact phrase as one bucket. More sophisticated multi-label exposure mapping is deferred until a versioned exposure taxonomy exists.

## Governance and audit
Every run records configuration hash, source scoring hash, holdings, reserves, exits, DCA allocation, retained-buffer names and constraint rejections. Universe removals remain governed by Universe Methodology v1.0; a weak price or score alone is not a universe-removal reason.
