# Winner Tilt Authorized Live SEC-to-Shadow Pilot v1.0

## Purpose

Milestone 17 adds a manual, explicitly authorized bridge between the bounded SEC EDGAR live ingest and the certified research-only shadow pipeline.

## Authorization gate

The workflow runs only through `workflow_dispatch`. The operator must provide:

- an active CIK present exactly once in `config/winner-tilt-security-identifiers-v1.0.0.csv`
- the exact phrase `AUTHORIZE_LIVE_SEC_SHADOW_RESEARCH_ONLY`
- an information cutoff, portfolio as-of date, and audit timestamp
- a configured `SEC_EDGAR_USER_AGENT` repository secret

Any mismatch blocks the run before network acquisition.

## Execution stages

1. Validate explicit authorization and active identifier linkage.
2. Run the existing bounded SEC EDGAR pilot with one allowed CIK and one maximum request.
3. Require exactly one immutable JSON snapshot.
4. Invoke the existing end-to-end certified shadow pilot.
5. Revalidate the execution boundary and hash the live snapshot and shadow manifest.
6. Upload the complete research artifact bundle for 30 days.

## Fail-closed conditions

The workflow stops on an invalid authorization phrase, invalid or unregistered CIK, missing SEC identity secret, multiple or missing snapshots, provider failure, downstream certification failure, artifact hash failure, or any executable boundary flag.

## Safety boundary

This workflow does not connect to a broker, create or execute orders, enable automatic DCA, enable automatic exits, schedule live acquisition, or produce an executable investment instruction. The dashboard output remains read-only and research-only.

## Manual run

Open GitHub Actions, select **Authorized Live SEC Shadow Pilot**, choose `main`, enter the required inputs, and run the workflow. Review `authorized-live-run-manifest.json` and all stage artifacts before treating the run as accepted research evidence.
