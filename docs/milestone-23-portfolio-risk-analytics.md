# Milestone 23 — Portfolio Risk Analytics Certification

Winner Tilt AI 2.7.0 adds deterministic, research-only portfolio risk analytics without changing upstream scoring, portfolio construction, replay, backtest, performance, or attribution rules.

## Certified analytics

- position HHI and effective number of positions
- maximum and top-three position concentration
- sector exposure and sector HHI
- diversification score
- portfolio volatility and downside volatility
- beta, tracking error, and information ratio versus an aligned benchmark
- largest holdings and deterministic concentration contributors
- historical readiness participation, preserving insufficient coverage as research-only

## Validation and lineage

The engine rejects uncertified replay/performance inputs, execution-boundary violations, duplicate positions, negative or non-normalized weights, non-finite values, and unordered or duplicated equity-curve observations. Reports bind to SHA256 hashes of the portfolio, performance certification, and historical replay manifest.

## Manual certification

Run the `Portfolio Risk Certification` workflow on `main` and select `AUTHORIZE_PORTFOLIO_RISK_RESEARCH_ONLY`. The workflow emits the risk report, research summary, manifest, input fixtures, diagnostic log, artifact hashes, and a manifest hash.

## Safety boundary

All outputs remain research-only. Broker connectivity, order creation, order execution, automatic DCA, and automatic exits remain disabled and are checked fail-closed.
