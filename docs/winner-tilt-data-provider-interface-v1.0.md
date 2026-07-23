# Winner Tilt Data Provider Interface v1.0

Providers implement `fetch(...)`, `validate(...)`, `metadata()`, and `latest_timestamp()`. Outputs include provider/vendor identity, acquisition timestamp, effective/as-of timestamp, optional publication timestamp, schema version, provenance metadata, and validation state.

The included implementations are deterministic in-memory synthetic providers for market data, fundamentals, estimates, corporate actions, benchmarks, and news. They perform no network calls and contain no credentials.

Provenance must include a replayable source reference, retrieval method, and license context. Production adapters for vendors remain pending and must preserve the same fail-closed validation contract.
