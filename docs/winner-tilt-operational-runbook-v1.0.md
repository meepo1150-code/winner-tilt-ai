# Winner Tilt Operational Runbook v1.0

Run order: acquire, validate, snapshot, Universe, Scoring, Portfolio, Research, Decision Journal, dashboard inputs. Stop after any failed required stage and investigate structured logs by execution ID.

Monitoring should alert on provider unavailability, stale snapshots, validation failures, missing dataset coverage, dashboard input absence, Decision Journal integrity failures, and production-readiness blockers.

Recovery: verify snapshot hashes, replay source references, rerun validation, then rerun scheduler with the original cutoff. Do not repair source data silently.

Deployment assumptions: UTC clocks, external secret manager, approved snapshot storage, backup retention for manifests and source payloads, and read-only dashboard publishing.

Remaining blockers: live vendor integrations, credentials, licensed datasets, real production operation, and investment performance evidence are pending.
