# Winner Tilt AI Fundamental Feature Integration v1.0

## Status

Milestone 12 adds an additive, deterministic bridge from normalized SEC EDGAR Company Facts to the frozen Winner Tilt scoring and point-in-time backtest contracts.

It does not modify scoring normalization, category weights, ranking, portfolio constraints, position sizing, turnover rules, or backtest execution logic.

## Data flow

1. `winner_tilt.data_providers.sec_edgar` acquires and normalizes Company Facts.
2. `winner_tilt.fundamental_features` applies a versioned feature mapping at an explicit UTC information cutoff.
3. The feature engine writes long-form observations with the exact columns consumed by `winner_tilt.scoring`.
4. Scoring output retains the cutoff and feature-output hash when assembled into a score vintage.
5. `winner_tilt.backtest` continues enforcing `available_at <= information_cutoff` before a vintage can be used.
6. `winner_tilt.portfolio` consumes the resulting frozen score run without changing any fundamental values.

## Supported feature operations

- `latest`: latest eligible published fact at the cutoff.
- `growth`: latest value divided by the previous comparable annual or quarterly period, minus one.
- `ratio`: latest numerator divided by a denominator from the same report end.

Mappings are defined in `config/winner-tilt-sec-fundamental-features-v1.0.0.json`. Concept aliases are ordered sets, allowing issuer taxonomy variation without embedding issuer-specific code in the engine.

## Point-in-time policy

A fact is eligible only when its normalized `accepted_timestamp` is less than or equal to the requested `information_cutoff`.

Later amendments replace an earlier filing only after the amendment publication timestamp becomes available. A backtest run before that timestamp continues to see the original filing.

Every valid observation records:

- `available_at`
- `report_end`
- source fact IDs
- source accession numbers
- peer group
- stale-critical state

Missing history or a missing same-period denominator becomes `TEMPORARILY_UNAVAILABLE`. Zero growth bases and zero ratio denominators fail closed because silently substituting a value would alter investment evidence.

## Scoring contract

The generated CSV contains:

```text
security_id,metric_id,value,missing_data_class,peer_group,stale_critical
```

This is the existing input contract of `winner_tilt.scoring`. No scoring-engine change is required.

## Backtest contract

`score_vintage_metadata(...)` emits:

- `information_cutoff`
- `generated_at`
- `fundamental_feature_output_sha256`
- the available-at policy

When score rows are assembled into the existing backtest vintage shape, each row must carry an `available_at` value no later than the vintage cutoff. The existing backtest loader remains the enforcing gate.

## CLI

```bash
python -m winner_tilt.fundamental_features \
  --facts reports/sec-edgar-live-pilot.json \
  --definitions config/winner-tilt-sec-fundamental-features-v1.0.0.json \
  --information-cutoff 2026-07-24T00:00:00Z \
  --output reports/fundamental-features.json \
  --scoring-csv reports/fundamental-observations.csv
```

## Safety and limitations

- The feature engine does not infer unavailable facts.
- It does not fetch network data.
- It does not treat a successful live pilot as investment-performance evidence.
- Cross-issuer concept coverage must be measured before production promotion.
- Market-price-dependent valuation metrics require a separately validated point-in-time market-data input and are outside this SEC-only mapping.
- The initial live pilot remains bounded to its approved CIK allowlist.

## Acceptance criteria

Milestone 12 is complete when:

- latest, growth, and ratio transformations are deterministic;
- future publications are excluded;
- amendments become visible only after publication;
- missing history is explicitly classified;
- zero denominators fail closed;
- scoring CSV compatibility is tested;
- score-vintage lineage metadata is tested;
- the full repository test suite passes in GitHub Actions.
