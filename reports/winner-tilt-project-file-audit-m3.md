# Winner Tilt AI — Project File Audit after Milestone 3

**Audit date:** 2026-07-23

## Delete and replace
| Existing file | Action | Replacement |
|---|---|---|
| `winner-tilt-schema-v1.0(2).sql` | Delete; exact duplicate | `winner-tilt-schema-v1.1.sql` |
| `winner-tilt-schema-v1.0(3).sql` | Delete after replacement | `winner-tilt-schema-v1.1.sql` |
| `winner-tilt-schema-m3-scoring-patch-v1.0.sql` | Delete after consolidating | Included in `winner-tilt-schema-v1.1.sql` |
| `winner-tilt-scoring-config-v1.0.0-prototype.json` | Delete | `winner-tilt-scoring-config-v1.0.0.json` |
| `winner-tilt-scoring-engine-v1.0.md` | Delete | `winner-tilt-scoring-engine-v1.0-frozen.md` |
| `winner-tilt-m3-implementation-report-v1.0.md` | Delete; superseded | `winner-tilt-m3-completion-report-v1.0.md` |
| `winner-tilt-spec-v1.0(3).md` | Delete | `winner-tilt-spec-v1.1.md` |
| `winner_tilt_scoring_engine_v1.py` | Replace in place | New final file with same name |
| `test_winner_tilt_scoring_engine_v1.py` | Replace in place | New discoverable 12-test suite |

## Keep unchanged
- `winner-tilt-data-model-v1.0(2).md`
- `winner-tilt-taxonomy-v1.0(2).csv`
- `universe-methodology-v1.0(3).md`
- `universe-v1.0(4).csv`
- `data-sources-v1.0(3).md`
- `winner-tilt-metric-registry-v1.0.csv`
- `winner-tilt-load-metric-registry-v1.0.sql`

## Upload as new files
- `winner-tilt-business-model-modules-v1.0.csv`
- `winner-tilt-synthetic-observations-v1.0.csv`
- `winner-tilt-prototype-score-run-v1.0.json`
- `winner-tilt-m3-test-results-v1.0.txt`
- `winner-tilt-m3-completion-report-v1.0.md`
- `winner-tilt-project-manifest-v1.1.json`

## Naming recommendation
Remove copy suffixes such as `(2)`, `(3)`, and `(4)` when the project repository is created. They are upload-history artifacts, not semantic versions.
