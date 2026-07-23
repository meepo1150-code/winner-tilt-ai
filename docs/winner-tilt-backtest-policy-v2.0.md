# Winner Tilt AI — Backtest Policy v2.0

**Status:** Frozen architecture; production result gate enforced  
**Milestone:** 5  
**Date:** 2026-07-23

## Purpose
Define a deterministic point-in-time walk-forward backtest for the frozen Winner Tilt scoring and portfolio rules. The backtest is a validation tool, not a rule-optimization tool.

## Frozen operating rules
- Information cutoff precedes every trade date.
- Monthly score vintages may update monitoring; trades occur only on the first available trading day in January and July.
- Portfolio target is 15 holdings.
- Default sizing is equal weight.
- Commission, spread and slippage are charged on traded notional.
- Benchmark must cover the same valuation dates.
- Ticker is never used as permanent identity.

## Production validity gate
A run may be labelled `PRODUCTION_VALID` only when the data manifest confirms all of the following:
1. point-in-time fundamentals;
2. point-in-time analyst estimates;
3. historical universe membership;
4. complete corporate actions;
5. delisted securities included;
6. complete benchmark history;
7. publication timestamps present;
8. independent look-ahead test passed.

The engine fails closed. Any missing gate or run-time integrity flag produces `VALIDATION_ONLY`.

## Output contract
- Daily portfolio and benchmark equity curves
- CAGR, annualized return, volatility, Sharpe, Sortino and maximum drawdown
- Benchmark-relative CAGR and ending-value spread
- Rebalance records and cumulative one-way turnover
- Full transaction ledger and transaction costs
- Integrity checks, failed gates and run flags

## Prohibited practices
- Reconstructing historical estimate revisions from current snapshots
- Using present-day universe membership for older dates
- Removing delisted failures from history
- Changing model weights merely to improve the backtest
- Presenting synthetic-fixture performance as investment evidence
