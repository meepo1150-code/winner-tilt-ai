# Winner Tilt Production Architecture v1.0

Milestone 9 adds production integration architecture only. The status is `PRODUCTION_INTEGRATION_ARCHITECTURE_COMPLETE_LIVE_INTEGRATIONS_PENDING`.

Workflow: acquire data, validate data, create immutable snapshots, invoke the existing Universe Engine, Scoring Engine, Portfolio Engine, Research Engine, create a Decision Journal entry, and publish read-only dashboard inputs. The scheduler orchestrates injected adapters and never reimplements frozen investment logic.

Point-in-time rules require UTC acquisition, publication, effective/as-of, and cutoff timestamps. Data fails closed when publication/effective/acquisition ordering is impossible, observations are stale or future-dated, provenance is missing, or schemas do not match.

Snapshots use canonical JSON, SHA-256 hashes, immutable manifest records, duplicate detection, and replayable source references compatible with Decision Journal linkage.

Secrets must be supplied through environment variables outside the repository. Backup and retention should preserve manifests, raw approved source references, and Decision Journal linkage. Recovery replays snapshots by content hash and cutoff.

Known limitations and blockers: live provider integrations are not included; real credentials are not included; licensed production datasets are not included; synthetic fixtures are not investment evidence; real-world performance validation remains pending.
