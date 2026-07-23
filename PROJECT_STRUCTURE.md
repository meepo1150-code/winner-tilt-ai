# Project Structure

Generated: 2026-07-23

## Top-Level Layout
- `apps/dashboard/` — Streamlit entry point for the read-only dashboard foundation.
- `src/winner_tilt/` — installable Python package containing the active engines and dashboard presentation helpers.
- `tests/` — automated Python test suites.
- `config/` — frozen runtime configuration and active project manifest.
- `database/` — SQL schemas, CSV datasets, registries, taxonomy, and synthetic observations.
- `docs/` — specifications, policies, data-source notes, interfaces, methodology, and upload guide.
- `reports/` — generated prototype outputs, milestone reports, test transcripts, and previous file-audit reports.
- `archive/` — obsolete but retained historical manifests/specifications and replaced prototype code.

## Active Engine Map
- Scoring: `winner_tilt.scoring` with `config/winner-tilt-scoring-config-v1.0.0.json`.
- Portfolio: `winner_tilt.portfolio` with `config/winner-tilt-portfolio-config-v1.0.0.json`.
- Backtest: `winner_tilt.backtest` with `config/winner-tilt-backtest-config-v2.0.0.json`.
- Research: `winner_tilt.research` with `config/winner-tilt-research-config-v1.0.0.json`.

## Archive Policy
Do not remove archived obsolete versions until references in reports/manifests are intentionally rewritten or a retention decision is approved.

## Dashboard Foundation
- Entry point: `apps/dashboard/streamlit_app.py`.
- Data/view-model helpers: `winner_tilt.dashboard`.
- Documentation: `docs/winner-tilt-dashboard-foundation-v1.0.md`.
- Dashboard dependencies are optional via `python -m pip install -e ".[dashboard]"`.

## Decision Journal
- Engine: `src/winner_tilt/decision_journal.py`.
- Contract/schema: `docs/winner-tilt-decision-journal-v1.0.md` and `database/winner-tilt-decision-journal-schema-v1.json`.
- Synthetic prototype JSONL: `reports/winner-tilt-m8-synthetic-prototype-decision-journal-v1.0.jsonl`.
- Dashboard consumption is read-only; the dashboard never creates or edits journal records.
