# Winner Tilt AI — Data Model Specification v1.0

**Milestone:** 2.5 Data Model Design  
**Status:** Frozen  
**Date:** 2026-07-23

## Purpose
Convert Winner Tilt AI into a versioned relational data model supporting monthly scoring, six-month universe reviews, 15 holdings and 15 reserves, DCA tracking, rebalancing, point-in-time backtests, research events, dashboards, APIs, and decision governance.

## Design principles
1. Permanent identity: company and security IDs do not depend on tickers.
2. Point-in-time history: mutable data is effective-dated instead of overwritten.
3. Controlled vocabularies: sectors, industries, stages, tiers, themes and exposures use IDs.
4. Many-to-many links: companies can have multiple themes and economic exposures.
5. Separation of layers: raw observations, metrics, scores, rankings and trades remain separate.
6. Auditability: rule changes and portfolio decisions are versioned.
7. Backtest safety: data stores when information became available.
8. Vendor neutrality: vendor symbols map to internal identifiers.

## Entity groups
### Security master
`companies`, `securities`, `security_identifiers`, `exchanges`, `countries`

### Classification
`sectors`, `industries`, `business_stages`, `quality_tiers`, `themes`, `economic_exposures`, `company_themes`, `company_exposures`

### Universe and eligibility
`universe_versions`, `universe_memberships`, `eligibility_reviews`, `eligibility_rule_results`

### Market and fundamentals
`price_daily`, `corporate_actions`, `fundamental_periods`, `fundamental_facts`, `estimate_snapshots`, `insider_transactions`

### Scoring
`scoring_models`, `scoring_model_versions`, `metric_definitions`, `metric_observations`, `score_runs`, `security_scores`, `score_components`, `rankings`

### Portfolio
`portfolio_policies`, `portfolio_policy_versions`, `portfolio_snapshots`, `portfolio_positions`, `rebalance_runs`, `rebalance_orders`, `dca_allocations`

### Governance
`research_events`, `event_security_links`, `decision_log`, `rule_change_log`, `data_quality_issues`

## Identity model
A company is the economic entity. A security is a tradable listing.

Example:
- `company_id = WT-C0001`
- `security_id = WT-S0001`
- `ticker = MSFT`
- `exchange_id = XNAS`

Ticker changes must not change the permanent IDs.

## Controlled enumerations
### Business stage
| ID | Code | Name |
|---|---|---|
| STG-01 | EMG | Emerging |
| STG-02 | GRW | Growth |
| STG-03 | MAT | Mature |

### Quality tier
| ID | Code | Name |
|---|---|---|
| QLT-01 | S | World Class |
| QLT-02 | A | Leader |
| QLT-03 | B | Strong |
| QLT-04 | C | Watchlist |

Quality tier remains metadata until Milestone 3 defines a repeatable rubric.

### Universe status
`ACTIVE`, `SUSPENDED`, `REMOVED`, `CANDIDATE`

## Theme taxonomy v1.0
1. AI Infrastructure
2. AI Software
3. Cloud Infrastructure
4. Enterprise Software
5. Cybersecurity
6. Semiconductors
7. Semiconductor Equipment
8. Networking & Connectivity
9. Robotics & Automation
10. Electrification
11. Digital Payments
12. Digital Commerce
13. Digital Advertising
14. Consumer Platforms
15. Healthcare Innovation
16. Life Science Tools
17. Defense
18. Aerospace
19. Space
20. Energy Infrastructure
21. Clean Power
22. Advanced Nuclear
23. Mobility
24. Logistics
25. Frontier Computing

Rules:
- one primary theme is required;
- zero to four secondary themes are allowed;
- theme changes require a taxonomy version update.

## Economic exposure taxonomy v1.0
1. AI & Data-Center Capex
2. Enterprise IT Spending
3. Cloud Workload Growth
4. Digital Advertising
5. Consumer Discretionary Spending
6. Consumer Staples Demand
7. Payment Volumes
8. Interest Rates & Credit
9. Capital-Market Activity
10. Healthcare Utilization
11. Drug Pipeline Execution
12. Biopharma R&D Spending
13. Industrial Production
14. Manufacturing Capex
15. Grid & Power Demand
16. Oil & Gas Prices
17. Defense Budgets
18. Commercial Aerospace Cycle
19. Travel Demand
20. Housing & Construction
21. Global Trade & Freight
22. Commodity & Farm Income
23. Regulatory Approval & Certification
24. Crypto & Retail Trading Activity
25. Frontier Technology Funding

Each link stores role, sensitivity, direction, valid-from and valid-to.

## Point-in-time rules
Backtest-sensitive tables must store:
- `observation_date`
- `available_at`
- `source_id`
- `ingested_at`
- `revision_number`, when relevant

A score run may only use information available at or before its information cutoff.

## Naming conventions
- database columns use `snake_case`;
- enum values use uppercase codes;
- dates use ISO `YYYY-MM-DD`;
- timestamps use UTC;
- percentages are decimals;
- monetary values store currency separately;
- soft deletion uses status or validity dates.

## Minimum viable implementation
The first working database requires:
`companies`, `securities`, `sectors`, `industries`, `business_stages`, `quality_tiers`, `themes`, `economic_exposures`, `company_themes`, `company_exposures`, `universe_versions`, `universe_memberships`, `eligibility_reviews`, `price_daily`, `metric_definitions`, `metric_observations`, `scoring_model_versions`, `score_runs`, `security_scores`, `rankings`, `portfolio_snapshots`, `portfolio_positions`, `decision_log`.

## Design freeze
- Company and security are separate entities.
- WT IDs are permanent and never reused.
- Ticker is not a primary key.
- Themes and exposures are many-to-many.
- Mutable classifications are effective-dated.
- Universe membership and eligibility are separate.
- Raw data, metrics, scores, rankings and trades are separate layers.
- Every score run references an immutable model version.
- `available_at` is mandatory for point-in-time backtesting.
- Quality tier cannot affect scores until a formal rubric is approved.
