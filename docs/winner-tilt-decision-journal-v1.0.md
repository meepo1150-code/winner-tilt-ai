# Winner Tilt AI Decision Journal v1.0

Milestone 8 adds a deterministic audit and explanation layer. The Decision Journal records what the system knew, decided, and displayed at each decision point. It does not call, edit, re-rank, rescore, resize, or otherwise interfere with frozen scoring, portfolio, backtest, research, or dashboard business logic.

## Implementation plan followed

1. Inspect existing project specifications, configs, reports, schemas, and the read-only dashboard view-model.
2. Identify existing identifiers: configuration hashes in scoring and portfolio outputs, data-manifest hash in backtest output, file paths and SHA-256 source snapshots, as-of dates, validation status, research non-interference flags, ranks, scores, holdings, reserves, weights, DCA allocation, entries, exits, and turnover.
3. Add a versioned journal contract and engine under `src/winner_tilt/decision_journal.py`.
4. Generate only synthetic/prototype validation records from existing prototype reports.
5. Extend the dashboard as a read-only consumer of journal JSONL.
6. Add tests for deterministic construction, canonical hashing, validation failures, integrity, dashboard integration, and non-interference.

## Missing production contracts

Production-grade journal creation is intentionally pending until the repository has durable production run IDs for each engine, production universe snapshot IDs, production source snapshot IDs with vendor/licensing provenance, dashboard/report publication IDs, and an approved retention backend. The Milestone 8 prototype records are validation-only and not investment evidence.

## Record contract summary

Each journal record uses contract version `winner-tilt-decision-journal-v1.0` and includes:

- `journal_record_id`, `run_id`, `decision_type`, `decision_timestamp_utc`, `effective_date`, `as_of_date`.
- System identifiers, config identifiers/hashes, source snapshot identifiers/hashes.
- Universe, score, portfolio, backtest, research, and dashboard/report references where applicable.
- Validation status, synthetic/prototype flag, input data cutoff.
- Selected holdings, reserves, ranks and scores, weights, DCA allocation, exits, entries, and turnover.
- Warnings, rationale/evidence references, non-interference attestation, and immutable SHA-256 record hash.

Supported decision types are `monthly_score_review`, `semiannual_rebalance`, `dca_allocation`, `backtest_validation`, `research_context_publication`, and `dashboard_snapshot_publication`.

## Validation and fail-closed rules

The journal engine rejects missing required fields, absolute paths, unsupported decision types, invalid UTC timestamps, input cutoffs after decision timestamps, evidence snapshots after the input cutoff, malformed run references, duplicate IDs/hashes, mismatched immutable hashes, and synthetic records that lack a clear “not investment evidence” warning. Inputs are deep-copied so record construction does not mutate engine outputs.

## Integrity and retention policy

Local journal output is append-only JSONL. Existing records are loaded and validated before appending. Duplicate `journal_record_id` values or duplicate immutable hashes are rejected. Reload integrity recomputes each record hash and produces a deterministic journal-chain SHA-256 over the ordered record hashes. Production retention should move JSONL to write-once object storage or a database table with immutable row hashes and access-controlled retention.

## Replay and reproducibility

To replay an audit record, retrieve every repository-relative evidence path listed in `rationale_evidence_refs`, verify each file SHA-256 and byte size, validate timestamps against `input_data_cutoff_utc`, recompute `immutable_record_hash`, and compare displayed holdings, reserves, scores, weights, DCA allocation, entries, exits, and turnover to the recorded fields. Replays must not regenerate or optimize decisions from current data.

## Prototype output

The prototype journal is `reports/winner-tilt-m8-synthetic-prototype-decision-journal-v1.0.jsonl`. It contains six records generated from existing prototype reports and is explicitly synthetic/prototype validation-only.
