# Winner Tilt AI — Walk-Forward Performance Analytics Certification v1.0

## Purpose

Milestone 21 certifies performance analytics produced by the existing point-in-time Backtest Engine and binds those metrics to the certified historical replay lineage from Milestone 20.

## Certified metrics

- total return
- CAGR
- annualized return
- annualized volatility
- Sharpe ratio
- Sortino ratio
- maximum drawdown
- benchmark-relative CAGR and ending-value spreads
- cumulative one-way turnover
- transaction costs
- portfolio-readiness participation rate

## Certification rules

The analytics layer independently recomputes portfolio and benchmark metrics from the equity curve and compares them with the Backtest Engine output using a strict numeric tolerance. Dates must be strictly increasing, values must be positive and finite, benchmark observations must align, and all source artifacts are SHA-256 bound.

`PERFORMANCE_CERTIFIED` is allowed only when the Backtest Engine reports `PRODUCTION_VALID`. A `VALIDATION_ONLY` backtest can be analyzed, but the analytics output remains `VALIDATION_ONLY`.

## Historical regression contracts

- ordered replay periods and no duplicate cutoffs
- certified M20 replay manifest required
- safe workflow choice authorization
- persistent diagnostics on failure
- all execution-boundary values remain false
- no metric certification when the underlying backtest is not production-valid
- no modification to scoring, portfolio, replay, or backtest rules

## Outputs

- `performance-certification.json`
- `performance-research-summary.json`
- `performance-certification-manifest.json`
- `performance-analytics-output.log`

All outputs are research-only. No broker connection, order creation, order execution, automatic DCA, or automatic exits are enabled.
