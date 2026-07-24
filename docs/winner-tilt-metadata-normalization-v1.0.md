# Winner Tilt AI — Metadata Normalization Decision

Status: `MILESTONE_10_METADATA_NORMALIZATION_APPROVED`

Issue: #10

## Canonical source

The active project manifest is the machine-readable canonical source for repository status. README, project structure, specifications, and completion reports are descriptive projections and must not independently redefine milestone status.

## Current inconsistency

The current active file is named `config/winner-tilt-project-manifest-v1.4.json` while its embedded `manifest_version` is `1.8`, and its `previous_manifest` field points to itself.

## Approved correction

A subsequent manifest-generation change must create `config/winner-tilt-project-manifest-v1.9.json` from the complete repository tree, with:

- embedded `manifest_version` equal to `1.9`
- `previous_manifest` equal to `config/winner-tilt-project-manifest-v1.4.json`
- no self-reference
- explicit self-hash exclusion
- complete deterministic file hashes generated from the final merged tree

The old manifest remains immutable until the full-tree manifest is generated. It must not be renamed or partially hand-edited because doing so would create unverifiable file hashes.

## Milestone 10 status vocabulary

- `MILESTONE_10_PHASE_B_IMPLEMENTED_LIVE_PILOT_DISABLED`
- `MILESTONE_10_LIVE_INGEST_APPROVED`
- `MILESTONE_10_DOWNSTREAM_CONSUMPTION_APPROVED`

This change reaches only the first status. Live ingest and downstream consumption require separate approval gates.

## Safety decision

Manifest v1.9 generation is intentionally deferred until the final Milestone 10 merge tree exists, so that hashes describe the actual repository state rather than an intermediate branch state.
