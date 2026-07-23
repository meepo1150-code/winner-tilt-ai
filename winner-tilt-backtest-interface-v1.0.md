# Winner Tilt AI — Backtest Engine Interface v1.0

**Status:** Interface frozen; production validation deferred  
**Date:** 2026-07-23

## Scope
Milestone 4 defines the contract between Portfolio Engine output and a future point-in-time walk-forward Backtest Engine. A lightweight prototype can value a supplied portfolio against adjusted-close data, but it is not evidence of production performance.

## Required inputs
- Versioned portfolio decision with security IDs and target weights
- Daily point-in-time price series keyed by `date`, `security_id`, `adjusted_close`
- Rebalance dates and target weights for each walk-forward period
- Commission, spread and slippage assumptions
- Benchmark prices
- Corporate actions and delisted-security returns

## Walk-forward rule
At each historical month-end, only data available at that time may create scores. Portfolio changes are executed only at the scheduled January/July rebalance after applying buffers, constraints and costs. Future observations may not leak into historical scores, universe membership or analyst estimates.

## Output contract
- Daily equity curve
- CAGR and annualized return
- Annualized volatility
- Sharpe and Sortino ratios
- Maximum drawdown
- Turnover and estimated transaction costs
- Hit rate / win rate when holding-period records exist
- Average holding period
- Exposure drift
- Benchmark-relative results
- Data-integrity and survivorship-bias flags

## Prototype limitations
The included prototype engine values one fixed target portfolio. It does not yet reconstruct monthly historical scoring, historical universe membership, delisted securities, analyst-estimate vintages or multi-period rebalances. Therefore its output must be labelled `PROTOTYPE_ONLY`.

## Production gate (Milestone 5)
Production backtesting requires the point-in-time datasets specified in Data Sources v1.0, test fixtures for delistings and corporate actions, benchmark integration, full transaction ledger, and independent anti-look-ahead validation.
