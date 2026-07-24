# Winner Tilt AI Shadow Audit and Dashboard Integration v1.0

Milestone 15 connects a certified Milestone 14 shadow portfolio to the existing append-only Decision Journal and the read-only dashboard presentation layer.

## Flow

1. Read one `SHADOW_RESEARCH_ONLY` payload.
2. Revalidate certification, immutable portfolio hash, unique holdings/reserves, lineage hashes, and all execution-boundary flags.
3. Build a `semiannual_rebalance` Decision Journal record using the existing journal contract.
4. Optionally append the record to a repository-relative JSONL store.
5. Build a presentation-only shadow dashboard view.

## CLI

```bash
python -m winner_tilt.shadow_audit \
  --shadow reports/shadow-portfolio.json \
  --vintage reports/certified-score-vintage.json \
  --universe config/universe-v1.0.csv \
  --root . \
  --decision-timestamp 2026-06-30T12:00:00Z \
  --run-id SHADOW-2026-06 \
  --output reports/shadow-audit-record.json \
  --journal reports/shadow-decision-journal.jsonl
```

## Fail-closed gates

The bridge blocks non-shadow inputs, uncertified inputs, executable flags, missing lineage, duplicate selections, portfolio hash mismatches, future information cutoffs, absolute evidence paths, and invalid journal records.

## Safety boundary

The dashboard is read-only. No broker is connected, no order is created or executed, and DCA or exit fields remain research output only. Scoring, portfolio, backtest, and Decision Journal business rules are unchanged.
