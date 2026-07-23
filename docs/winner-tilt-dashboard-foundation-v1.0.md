# Winner Tilt AI Dashboard Foundation v1.0

Milestone 7 adds a lightweight, local-first Streamlit dashboard for read-only presentation of existing Winner Tilt AI outputs.

## Scope

- The dashboard loads repository-relative JSON snapshots from `reports/`.
- It displays project status, holdings, reserves, scores, ranks, portfolio weights, DCA allocation, concentration summary, backtest metrics, research events, freshness metadata, source timestamps, and validation status.
- It fails closed when required input files or required top-level fields are missing.
- It labels synthetic, prototype, stale, and validation-only inputs as warnings.

## Non-interference policy

The dashboard is presentation-only. It does not call or modify the frozen scoring, portfolio, backtest, or research engines. Research signals remain informational context and must not alter scores, rankings, holdings, reserves, weights, DCA, turnover, exits, or backtest decisions.

## Data contracts

Required report inputs are centralized in `winner_tilt.dashboard.DEFAULT_INPUTS` and validated by `winner_tilt.dashboard.REQUIRED`.

Missing production contracts identified during Milestone 7:

- No deployment-time dashboard data API exists yet; the dashboard consumes milestone JSON snapshots.
- No formal freshness SLA exists by report type; Milestone 7 uses a conservative presentation warning threshold.
- Prototype reports include synthetic and validation-only records; these are not investment evidence.

## Run command

```bash
python -m pip install -e ".[dashboard]"
python -m streamlit run apps/dashboard/streamlit_app.py
```
