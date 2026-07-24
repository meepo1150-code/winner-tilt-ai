# Winner Tilt Certified Shadow Portfolio v1.0

Milestone 14 connects one certified Milestone 13 score vintage to the existing Portfolio Engine without changing portfolio business logic.

## Command

```bash
python -m winner_tilt.shadow_portfolio \
  --vintage path/to/certified-score-vintage.json \
  --portfolio-config config/portfolio.json \
  --universe database/universe-v1.0.csv \
  --as-of-date 2026-07-24 \
  --output reports/shadow-portfolio.json
```

## Certification gates

The bridge requires exactly one certified vintage, non-empty immutable lineage, a cutoff no later than the shadow as-of date, unique security identifiers, unique positive ranks for eligible securities, and `available_at` timestamps no later than the information cutoff. It invokes `winner_tilt.portfolio` as an isolated subprocess and validates holdings, reserves, unique selections, and weights after execution.

## Output boundary

The resulting holdings, reserves, exits, and DCA allocation are research-only shadow output. The envelope explicitly records that no broker is connected, no orders are created or executed, and no automatic DCA or exit action is permitted.

## Non-interference

Milestone 14 does not alter scoring formulas, rank rules, portfolio concentration constraints, rebalance buffers, turnover controls, or position sizing. It only certifies inputs, invokes the frozen engine, validates its output contract, and attaches deterministic hashes.
