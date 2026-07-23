# Winner Tilt AI

Winner Tilt AI is a deterministic research prototype for ranking a curated equity universe, constructing a constrained portfolio, validating point-in-time backtest inputs, and summarizing timestamped research context.

## Project overview

The repository contains four active Python engines packaged under `winner_tilt`:

- `winner_tilt.scoring` — deterministic metric normalization and scoring.
- `winner_tilt.portfolio` — portfolio and reserve selection with concentration, turnover, and sizing controls.
- `winner_tilt.backtest` — point-in-time-aware walk-forward backtest architecture.
- `winner_tilt.research` — timestamped event validation and research-context summarization.

## Directory structure

```text
.
├── archive/              # Historical manifests, specs, and replaced prototype code
├── config/               # Frozen runtime configuration and active project manifest
├── database/             # CSV datasets, registries, taxonomy, and SQL schemas
├── docs/                 # Specifications, policies, interfaces, methodology, and guides
├── reports/              # Generated milestone reports, test transcripts, and prototype outputs
├── src/winner_tilt/      # Installable Python package with active engines
└── tests/                # Automated test suites
```

## Quick start

Use Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

No third-party runtime packages are required by the active engines. Runtime dependencies remain empty.

For development and test work, install the package with the optional development dependencies:

```bash
python -m pip install -e ".[dev]"
```

## Test command

```bash
python -m compileall src tests
python -m pytest -q
```

## Repository layout

- Active engine source lives in `src/winner_tilt/`.
- Tests import the package modules directly from `winner_tilt`.
- Historical files remain in `archive/` and should not be deleted without a retention decision.
- Generated reports and prototype output snapshots live in `reports/`.
