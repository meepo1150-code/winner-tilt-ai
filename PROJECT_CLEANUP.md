# Project Cleanup

Generated: 2026-07-23

## Actions Completed
- Created branch `cleanup/project-v2`.
- Moved executable Python engines into `src/`.
- Moved tests into `tests/` and updated imports/fixtures to use repository-relative paths.
- Moved JSON configuration and active project manifest into `config/`.
- Moved SQL schemas and CSV datasets/registries into `database/`.
- Moved policy/spec/source methodology documents into `docs/`.
- Moved milestone reports, prior audit reports, test transcripts, and prototype run outputs into `reports/`.
- Moved obsolete versioned manifests/specs and the replaced v1 backtest prototype into `archive/`.
- Rebuilt the active manifest with cleaned relative paths and current SHA-256 values.

## Deletions
No referenced file content was deleted. Cleanup was performed via directory moves and archival of obsolete versions.

## Import Updates
- Backtest and scoring tests now load engine modules from `src/`.
- Research tests now load the engine from `src/` and config from `config/`.
- Portfolio tests now import from `src/` and load config/data/report fixtures from their cleaned directories.

## Validation
`python -m pytest -q` passed all 35 tests.

## Phase 2 Modernization
- Converted active engines into the `winner_tilt` package under `src/winner_tilt/`.
- Added `pyproject.toml`, `requirements.txt`, GitHub Actions test workflow, and `README.md`.
- Updated tests to import package modules directly.
