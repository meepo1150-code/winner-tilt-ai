# Project Structure

Generated: 2026-07-23

## Top-Level Layout
- `src/winner_tilt/` — installable Python package containing the active engines.
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
