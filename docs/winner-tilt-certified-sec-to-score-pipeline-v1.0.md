# Winner Tilt Certified SEC-to-Score Pipeline v1.0

## Purpose

Milestone 13 connects the bounded SEC EDGAR snapshot produced by Milestone 11 to the point-in-time feature bridge from Milestone 12 and the existing frozen scoring engine. The output is a certified score-vintage envelope accepted by the existing backtest loader.

## Execution boundary

The pipeline does not construct a portfolio, allocate DCA cash, create exits, write investment decisions to the journal, or publish dashboard recommendations. Scoring formulas, normalization, ranking, portfolio constraints, and backtest execution remain unchanged.

## Identifier linkage

SEC Company Facts rows use a ten-digit CIK. Winner Tilt engines use `WT_ID`. The pipeline resolves identifiers only through `config/winner-tilt-security-identifiers-v1.0.0.csv`.

Rules:

- only `ACTIVE` mappings are consumed;
- each CIK must map to exactly one `WT_ID`;
- each `WT_ID` must map to exactly one CIK;
- unmapped CIKs fail closed;
- ticker and company-name inference is prohibited.

The initial registry contains only the approved Apple pilot linkage `0000320193 -> WT-0005`.

## Certification gates

Before feature creation, the pipeline verifies:

- dataset type is `fundamentals`;
- provider is `sec-edgar-companyfacts`;
- the M11 pilot tag is present;
- provenance and source-content hash are present;
- raw-payload retention remains disabled;
- normalized rows are non-empty and row IDs are unique;
- required SEC metadata is present;
- every fact publication timestamp is at or before the information cutoff;
- acquisition time does not precede publication.

The embedded `validation_state` is not trusted because M11 writes an immutable provider result after validation without mutating that field. M13 performs certification again from the snapshot evidence.

## Pipeline order

1. Load and certify the immutable SEC snapshot.
2. Load and validate the versioned CIK-to-WT identifier registry.
3. Replace source CIK security IDs with mapped Winner Tilt IDs while preserving `source_security_id`.
4. Build point-in-time observations with `winner_tilt.fundamental_features`.
5. Write the exact long-form CSV contract consumed by the frozen scoring engine.
6. Invoke `python -m winner_tilt.scoring` in an isolated temporary directory.
7. Validate score IDs and per-security availability timestamps.
8. Emit one backtest-compatible vintage with immutable lineage hashes.

## Lineage

Each vintage records hashes for:

- snapshot file bytes;
- canonical snapshot payload;
- SEC raw content reference;
- identifier registry;
- feature definitions;
- fundamental feature output;
- scoring configuration;
- universe;
- scoring output;
- pipeline version.

## CLI

```bash
python -m winner_tilt.sec_to_score \
  --snapshot path/to/CIK0000320193.json \
  --identifier-registry config/winner-tilt-security-identifiers-v1.0.0.csv \
  --feature-definitions config/winner-tilt-sec-fundamental-features-v1.0.0.json \
  --scoring-config path/to/frozen-scoring-config.json \
  --universe database/universe-v1.0.csv \
  --information-cutoff 2026-07-24T00:00:00Z \
  --output reports/certified-sec-score-vintage.json
```

Exit code `2` means the pipeline was blocked by a fail-closed gate.

## Validation status

Passing tests prove deterministic contract integration using fixtures and the real scoring CLI. They do not establish investment performance, production-wide issuer coverage, or approval for automatic portfolio consumption.
