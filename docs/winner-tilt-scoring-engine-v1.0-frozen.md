# Winner Tilt AI — Scoring Engine Specification v1.0

**Milestone:** 3 — Scoring Engine Design
**Freeze date:** 2026-07-23  
**Status:** Frozen  
**Date:** 2026-07-23  
**Applies to:** Universe v1.0 (96 securities: 80 Core, 16 Emerging)

## 1. Objective

Rank every eligible security in the frozen Winner Tilt AI universe once per month using only information available by the score run's `information_cutoff`.

The scoring engine produces research rankings, not automatic trades. Portfolio changes remain restricted to scheduled six-month rebalances under a separate portfolio policy.

## 2. Locked principles

1. Hard eligibility filters run before scoring.
2. Every score run references an immutable scoring-model version and universe version.
3. Raw observations, derived metrics, normalized scores, composite scores, rankings, and portfolio decisions remain separate.
4. No observation with `available_at > information_cutoff` may enter a score run.
5. Market regime is not part of an individual stock score.
6. Sector, theme, economic exposure, business stage, quality tier, and universe pool remain distinct metadata.
7. Quality tier is not a scoring input in model v1.0; it remains metadata until independently validated.
8. Monthly rankings do not trigger trades.
9. Rules cannot be changed solely because another version produces a better historical return.

## 3. Score architecture

Each eligible security receives seven category scores on a 0–100 scale:

- Growth
- Quality
- Financial Strength
- Valuation
- Momentum
- Capital Allocation
- Risk

The total score is the weighted sum of category scores minus explicit data-quality penalties.

```text
total_score = sum(category_score × stage_weight) - missing_data_penalty
```

Final score range is clamped to 0–100.

## 4. Business-stage weights

The universe contains materially different financial profiles. A single weighting scheme would systematically favor profitable mature firms or, in the opposite direction, high-growth firms with weak economics. Model v1.0 therefore uses stage-specific weights while preserving the same seven-category architecture.

| Category | Emerging | Growth | Mature |
|---|---:|---:|---:|
| Growth | 30% | 25% | 15% |
| Quality | 20% | 25% | 30% |
| Financial Strength | 20% | 15% | 20% |
| Valuation | 10% | 15% | 20% |
| Momentum | 10% | 10% | 5% |
| Capital Allocation | 5% | 5% | 5% |
| Risk | 5% | 5% | 5% |
| **Total** | **100%** | **100%** | **100%** |

### Rationale

- **Emerging:** rewards scale-up but applies stronger cash-runway, dilution, and financial-survival treatment.
- **Growth:** balances structural growth, business quality, and valuation.
- **Mature:** emphasizes durable returns, balance-sheet strength, cash generation, and valuation.

## 5. Metric set

### 5.1 Growth

| Metric ID | Metric | Direction | Default metric weight |
|---|---|---|---:|
| GRW_REV_1Y | Revenue growth, trailing 12 months YoY | Higher | 25% |
| GRW_REV_3Y | Revenue CAGR, 3 fiscal years | Higher | 25% |
| GRW_EPS_1Y | Diluted EPS growth, TTM YoY | Higher | 15% |
| GRW_FCF_1Y | Free-cash-flow growth, TTM YoY | Higher | 15% |
| GRW_GM_DELTA | Gross-margin change, TTM vs prior TTM | Higher | 10% |
| GRW_OM_DELTA | Operating-margin change, TTM vs prior TTM | Higher | 10% |

Stage rules:
- For Emerging firms with negative EPS or FCF in both periods, `GRW_EPS_1Y` and `GRW_FCF_1Y` are not treated as ordinary percentage growth. They are replaced by operating-loss improvement and FCF-burn improvement respectively.
- Mature firms place less category weight on growth, but the internal metric mix remains stable in v1.0.

### 5.2 Quality

| Metric ID | Metric | Direction | Weight |
|---|---|---|---:|
| QLT_ROIC | Return on invested capital, TTM | Higher | 25% |
| QLT_GM | Gross margin, TTM | Higher | 15% |
| QLT_OM | Operating margin, TTM | Higher | 20% |
| QLT_FCFM | Free-cash-flow margin, TTM | Higher | 20% |
| QLT_CASH_CONV | FCF / adjusted net income, 3-year median | Higher | 10% |
| QLT_STABILITY | Operating-margin stability, 12-quarter dispersion | Lower | 10% |

Rules:
- ROIC is not scored for pre-profit Emerging firms where invested-capital economics are not yet meaningful; the weight is redistributed inside Quality without penalty.
- Extremely high cash conversion caused by depressed or near-zero net income is capped before normalization.

### 5.3 Financial Strength

| Metric ID | Metric | Direction | Weight |
|---|---|---|---:|
| FIN_NET_DEBT_EBITDA | Net debt / EBITDA | Lower | 25% |
| FIN_INTEREST_COVER | EBIT / interest expense | Higher | 20% |
| FIN_CURRENT_RATIO | Current ratio | Higher | 10% |
| FIN_NET_CASH_ASSETS | Net cash / total assets | Higher | 15% |
| FIN_DEBT_TREND | Net debt change over 12 months | Lower | 10% |
| FIN_RUNWAY | Cash runway in months | Higher | 20% |

Stage rules:
- `FIN_RUNWAY` is mandatory for Emerging firms with negative TTM FCF.
- For financial institutions, industrial-company leverage metrics are not used. A sector-specific financials module must replace them before those names receive production scores. Until that module exists, affected names are flagged `MODEL_LIMITATION` rather than silently imputed.

### 5.4 Valuation

Valuation uses stage-specific metric modules. A metric is scored only when economically meaningful.

#### Emerging module

| Metric ID | Metric | Direction | Weight |
|---|---|---|---:|
| VAL_EV_SALES_FWD | Forward EV / sales | Lower | 40% |
| VAL_EV_GP | EV / gross profit, TTM | Lower | 25% |
| VAL_GROWTH_ADJ | EV/sales divided by expected revenue growth | Lower | 25% |
| VAL_FCF_YIELD | FCF yield, where positive | Higher | 10% |

#### Growth module

| Metric ID | Metric | Direction | Weight |
|---|---|---|---:|
| VAL_EV_SALES_FWD | Forward EV / sales | Lower | 25% |
| VAL_EV_EBITDA_FWD | Forward EV / EBITDA | Lower | 25% |
| VAL_PEG_FWD | Forward P/E divided by forward EPS growth | Lower | 20% |
| VAL_FCF_YIELD | FCF yield, TTM | Higher | 20% |
| VAL_REL_HISTORY | Valuation percentile vs own 5-year history | Lower | 10% |

#### Mature module

| Metric ID | Metric | Direction | Weight |
|---|---|---|---:|
| VAL_PE_FWD | Forward P/E | Lower | 25% |
| VAL_EV_EBITDA_FWD | Forward EV / EBITDA | Lower | 25% |
| VAL_FCF_YIELD | FCF yield, TTM | Higher | 30% |
| VAL_REL_HISTORY | Valuation percentile vs own 5-year history | Lower | 20% |

Rules:
- Negative-denominator multiples are marked not meaningful, not ranked as cheap.
- Estimate-based metrics require a licensed point-in-time estimate snapshot in production backtests.
- If point-in-time estimates are unavailable, the run must use a separately versioned trailing-only valuation module and cannot be labeled production-grade.

### 5.5 Momentum

| Metric ID | Metric | Direction | Weight |
|---|---|---|---:|
| MOM_RS_6M | 6-month total return minus benchmark | Higher | 30% |
| MOM_RS_12M | 12-month total return minus benchmark | Higher | 30% |
| MOM_TREND_200D | Price / 200-day moving average minus 1 | Higher | 15% |
| MOM_EPS_REV_3M | 3-month forward EPS estimate revision | Higher | 15% |
| MOM_REV_REV_3M | 3-month forward revenue estimate revision | Higher | 10% |

Rules:
- The most recent 20 trading days are excluded from 12-month momentum to reduce short-term reversal effects.
- Estimate-revision metrics are disabled when point-in-time estimates are unavailable; their weights are redistributed only in a separately identified prototype configuration.

### 5.6 Capital Allocation

| Metric ID | Metric | Direction | Weight |
|---|---|---|---:|
| CAP_SHARE_CHANGE | Diluted share-count change, YoY | Lower | 35% |
| CAP_SBC_REVENUE | Stock-based compensation / revenue, TTM | Lower | 20% |
| CAP_BUYBACK_YIELD | Net repurchase yield, TTM | Higher | 20% |
| CAP_ROIC_TREND | ROIC change, 3-year trend | Higher | 15% |
| CAP_INSIDER | Net discretionary insider-buying signal | Higher | 10% |

Rules:
- Emerging firms receive a two-times penalty sensitivity for excessive dilution inside `CAP_SHARE_CHANGE`.
- Routine option exercises, tax withholding, and compensation grants are separated from discretionary open-market insider transactions.

### 5.7 Risk

| Metric ID | Metric | Direction | Weight |
|---|---|---|---:|
| RSK_VOL_1Y | Annualized daily volatility, 1 year | Lower | 25% |
| RSK_DRAWDOWN_3Y | Maximum drawdown, 3 years | Lower magnitude | 25% |
| RSK_BETA_2Y | Absolute beta deviation above 1, 2 years | Lower | 10% |
| RSK_EARN_VOL | Quarterly EPS or operating-income volatility | Lower | 15% |
| RSK_DILUTION | Diluted share-count growth, 3-year CAGR | Lower | 15% |
| RSK_EVENT_FLAG | Active severe governance, solvency, or listing-risk flag | Lower | 10% |

Risk is deliberately limited to 5% of total score. It should distinguish fragile from durable candidates without mechanically turning Winner Tilt AI into a low-volatility strategy.

## 6. Metric calculation rules

### 6.1 Observation selection

For each metric and security, use the newest valid observation satisfying:

```text
available_at <= score_run.information_cutoff
observation_date <= score_run.as_of_date
```

If revised fundamentals exist, select the highest revision number that was available by the cutoff. Later revisions cannot overwrite the historical score run.

### 6.2 Frequency and staleness

- Market metrics: update monthly using daily prices through the cutoff.
- Fundamental metrics: update when new filings or earnings materials become available.
- Estimate metrics: use the latest snapshot at or before cutoff.
- Insider metrics: use filing availability time, not transaction date alone.

Default staleness limits:
- Price metrics: 5 trading days.
- Quarterly fundamentals: 150 calendar days.
- Annual-only fundamentals: 450 calendar days.
- Estimates: 45 calendar days.

Stale observations are treated as unavailable and recorded as a data-quality issue.

## 7. Outlier treatment and normalization

### 7.1 Transformations

Before ranking:

1. Apply metric-specific validity checks.
2. Winsorize valid observations at the 5th and 95th percentiles of the eligible comparison group.
3. Convert the winsorized value to a percentile score from 0 to 100.
4. Reverse the percentile for lower-is-better metrics.

Percentile scoring is chosen because it is transparent and less sensitive to extreme values than a conventional z-score.

### 7.2 Comparison groups

- Momentum: entire eligible universe.
- Valuation: business stage, then sector/industry when at least six valid peers exist.
- Profitability and margins: blended peer score.
- Financial strength: business stage plus business-model module.
- Risk: entire universe, except earnings volatility may use stage peers.

Blended peer score:

```text
normalized_score = 0.70 × stage_or_sector_percentile
                 + 0.30 × universe_percentile
```

If the primary comparison group has fewer than six valid securities, use the universe percentile alone and flag `SMALL_PEER_GROUP`.

### 7.3 Ties

Ties are resolved in this order:

1. Higher Quality category score.
2. Higher Financial Strength category score.
3. Higher 12-month relative-strength score.
4. Lower permanent `security_id` for deterministic output.

## 8. Missing-data treatment

Missing values are divided into three classes.

### A. Not applicable

The metric is economically meaningless for the company type, such as P/E for a loss-making firm. Its weight is redistributed among valid metrics in the same category. No penalty applies.

### B. Temporarily unavailable

The metric should exist but is unavailable, stale, or has failed validation. Its score is temporarily set to 50 and a penalty applies.

### C. Structurally unsupported

The present model lacks an appropriate module, such as bank-specific capital and credit metrics. The security receives a model-limitation flag. It may be ranked only in prototype mode; production mode must exclude it until the module is implemented.

### Coverage thresholds

- Minimum total weighted metric coverage: 80%.
- Minimum category coverage: 60% for any category weighted at 15% or more.
- Emerging firms with negative FCF must have a valid cash-runway metric.
- A security failing a mandatory requirement is `eligible = false` for that score run.

### Penalty formula

```text
missing_data_penalty = min(10,
    0.20 × unavailable_weight_percentage
    + 2 × stale_critical_metric_count
)
```

Examples:
- 10% temporarily unavailable metric weight → 2-point penalty.
- 25% temporarily unavailable metric weight → 5-point penalty.
- Penalty is capped at 10 points.

## 9. Category and total score calculation

For each category:

```text
category_score = sum(metric_score × adjusted_metric_weight)
```

Adjusted metric weights sum to 100% after removing not-applicable metrics.

Total score:

```text
pre_penalty_score = sum(category_score × stage_category_weight)
total_score = max(0, min(100, pre_penalty_score - missing_data_penalty))
```

Required stored outputs:

- total score
- seven category scores
- each normalized metric score
- raw metric value
- comparison group
- effective metric weight
- missing-data class
- penalty contribution
- eligibility status
- all data-quality flags

## 10. Ranking status

Monthly score runs assign research status only:

| Status | Definition |
|---|---|
| PORTFOLIO | Existing portfolio holding; status does not imply a monthly trade |
| RESERVE | Current reserve list member |
| WATCH | Eligible but not in portfolio or reserve list |
| INELIGIBLE | Failed hard filter, mandatory coverage, or model support |

The monthly rank table must preserve current portfolio/reserve membership separately from raw rank. Rank alone must not overwrite portfolio state.

## 11. Six-month entry and exit buffer

The portfolio always targets 15 holdings. Rebalance logic uses rank hysteresis to reduce turnover.

### Hard exit

An incumbent exits if any condition is true:

- ineligible at the rebalance date;
- removed or suspended from the active universe;
- active severe governance/listing/solvency rule requires forced removal;
- rank is below 25.

### Protected hold zone

An eligible incumbent ranked 1–20 is normally retained.

### Challenge zone

An incumbent ranked 21–25 may be replaced only when an eligible non-holding:

- ranks at least five places higher; and
- is inside the top 15 overall after concentration constraints.

### Vacancy filling

After hard exits and valid challenges, vacancies are filled by the highest-ranked eligible non-holdings that pass portfolio concentration constraints.

### Reserve list

The 15 highest-ranked eligible non-holdings after the rebalance become reserves. Reserve status does not authorize automatic purchase between rebalance dates.

### Emergency replacement

Between scheduled rebalances, a holding may be replaced only for acquisition, delisting, trading suspension, investability failure, or a pre-defined severe governance/solvency event. Price decline or monthly rank deterioration alone is insufficient.

## 12. Concentration-control interface

The scoring engine ranks securities independently. It must also expose the metadata required by the Portfolio Engine:

- sector
- universe group
- primary and secondary themes
- economic exposures and sensitivity
- Core/Emerging pool
- business stage

Concentration controls are applied after ranking. They do not alter individual stock scores in model v1.0.

This separation prevents a company's score from changing merely because other companies are already held.

## 13. Quality-tier policy

Existing S/A/B/C quality tiers remain descriptive metadata in scoring model v1.0.

They must not:

- add bonus points;
- change metric weights;
- determine eligibility;
- resolve ranking ties.

Reason: the current tiers are qualitative and were assigned before a reproducible rubric existed. Using them now would double-count judgment already reflected in universe construction and could embed confirmation bias.

A future quality-tier rubric may be approved only if:

1. each criterion is observable and repeatable;
2. two independent reviewers can reach materially similar results;
3. historical assignments are point-in-time reconstructable;
4. the rubric adds information beyond quantitative Quality metrics;
5. it is versioned and tested out-of-sample.

## 14. Model configurations

### Production configuration

Requires:

- point-in-time fundamentals;
- point-in-time estimate history;
- adjusted prices and corporate actions;
- historical universe membership;
- delisted securities where relevant;
- filing and publication timestamps.

### Prototype configuration

May use trailing-only valuation and omit historical estimate revisions, but must:

- carry a `PROTOTYPE_NOT_PIT_COMPLETE` flag;
- use a distinct scoring-model version;
- never be presented as a production-grade backtest.

## 15. Model versioning and governance

Every model version freezes:

- metric definitions and formulas;
- stage weights;
- metric weights;
- transformations;
- comparison groups;
- missing-data rules;
- staleness thresholds;
- ranking tie-breakers;
- portfolio buffer parameters.

A model change requires:

1. change proposal;
2. economic rationale stated before backtest review;
3. impact analysis;
4. decision-log entry;
5. new immutable model version;
6. effective date.

Parameter searches that select the best historical result without economic justification are prohibited.

## 16. Minimum validation tests before freeze

1. **Determinism:** same inputs produce identical scores and ranks.
2. **Point-in-time test:** later filings and revisions cannot affect earlier runs.
3. **Direction test:** improving a higher-is-better metric cannot reduce its metric score.
4. **Missing-data test:** not-applicable and unavailable values receive different treatment.
5. **Stage test:** negative-EPS Emerging names are not falsely classified as cheap.
6. **Outlier test:** a single extreme value cannot dominate the category.
7. **Coverage test:** mandatory metric failures make the security ineligible.
8. **Turnover test:** entry/exit buffers reduce unnecessary six-month churn.
9. **Concentration interface test:** required theme and exposure fields are present.
10. **Audit test:** every final score can be reconstructed from stored observations and model configuration.

## 17. Known limitations of v1.0

- Banks, insurers, and some REIT-like business models require specialized financial-strength and valuation modules.
- Forward valuation and estimate-revision history cannot be backtested correctly from current estimates.
- A 16-name Emerging pool produces coarse peer percentiles; blended universe percentiles reduce but do not eliminate this limitation.
- Percentile scores measure relative attractiveness, not absolute investment merit.
- Category weights encode policy judgments and must be validated through sensitivity tests rather than assumed optimal.
- The scoring engine does not forecast macroeconomic regimes or portfolio-level correlations.

## 18. Milestone 3 completion criteria

Milestone 3 is complete when:

- this specification is approved and frozen;
- the metric registry is loaded into `metric_definitions`;
- scoring schema supports category and component-level audit records;
- one deterministic prototype score run completes for all 96 securities;
- failed and unsupported metrics are visible rather than silently imputed;
- ranking and six-month buffer unit tests pass;
- scoring model v1.0 is stored as immutable configuration JSON.

## 19. Recommended implementation sequence

1. Patch the SQL schema to store score components, category scores, flags, and model configuration.
2. Load metric registry v1.0.
3. Build price-derived metrics first.
4. Build trailing fundamental metrics from SEC/company data.
5. Add point-in-time estimate metrics only after the data source is selected.
6. Run a data-coverage audit across all 96 names.
7. Implement prototype normalization and scoring.
8. Validate rank stability and missing-data behavior.
9. Freeze Scoring Engine v1.0.
10. Proceed to Backtest Engine design.


## 20. Validation completion

Milestone 3 validation used a deterministic synthetic fixture covering all 96 securities. The fixture validates software behavior, auditability, missing-data handling, ranking determinism, and unsupported-business-model exclusions. It is not market data and its ranks must never be interpreted as investment recommendations. Production score runs require point-in-time observations from approved sources.
