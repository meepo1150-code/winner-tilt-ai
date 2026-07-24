# Winner Tilt End-to-End Certified Shadow Pilot v1.0

## Purpose

Milestone 16 connects the existing certified stages into one reversible research-only workflow:

1. explicit immutable SEC snapshot
2. point-in-time fundamental observations and certified score vintage
3. certified shadow portfolio
4. validated Decision Journal record
5. read-only dashboard shadow view
6. immutable run manifest

The workflow never performs a live SEC fetch by itself and never connects to a broker.

## CLI

```bash
python -m winner_tilt.shadow_pilot \
  --snapshot artifacts/sec-edgar/CIK0000320193.json \
  --identifier-registry config/winner-tilt-security-identifiers-v1.0.0.csv \
  --feature-definitions config/winner-tilt-sec-fundamental-features-v1.0.0.json \
  --scoring-config config/winner-tilt-scoring-config-v1.0.0.json \
  --portfolio-config config/winner-tilt-portfolio-config-v1.0.0.json \
  --universe database/universe-v1.0.csv \
  --output-dir artifacts/shadow-pilot \
  --information-cutoff 2026-02-01T00:00:00Z \
  --as-of-date 2026-02-01 \
  --decision-timestamp 2026-02-01T01:00:00Z \
  --run-id shadow-example-1
```

All input and output paths must be repository-relative. A run directory is immutable: the same run ID cannot overwrite an existing run.

## Artifacts

Each run emits:

- `certified-score-vintage.json`
- `certified-shadow-portfolio.json`
- `decision-journal-record.json`
- `dashboard-shadow-view.json`
- `run-manifest.json`

The manifest records stage status and SHA-256 hashes for every preceding artifact.

## GitHub Actions

The manual `Certified Shadow Pilot` workflow accepts only a repository-relative SEC snapshot path and explicit timestamps. It does not call the live SEC transport. Artifacts are retained for 30 days.

## Fail-closed conditions

The run is blocked for missing or escaping paths, reused run IDs, failed upstream certification, future information, invalid hashes, missing artifacts, or any execution-boundary flag set to true.

## Safety boundary

- broker connection: disabled
- order creation: disabled
- order execution: disabled
- automatic DCA: disabled
- automatic exits: disabled
- dashboard recommendations: disabled
- live SEC fetch: separate explicit workflow only
