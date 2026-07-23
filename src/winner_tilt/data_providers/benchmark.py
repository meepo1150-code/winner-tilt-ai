"""Offline benchmark provider."""
from .base import InMemoryProvider, ProviderMetadata
class BenchmarkProvider(InMemoryProvider):
    def __init__(self, rows, *, acquired_at, effective_at, published_at=None, provenance=None, provider_id="synthetic-benchmark", vendor="Winner Tilt Synthetic"):
        super().__init__(ProviderMetadata(provider_id, vendor, "benchmark"), rows, acquired_at=acquired_at, effective_at=effective_at, published_at=published_at, provenance=provenance)
