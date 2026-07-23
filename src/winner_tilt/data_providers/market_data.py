"""Offline market_data provider."""
from .base import InMemoryProvider, ProviderMetadata
class MarketDataProvider(InMemoryProvider):
    def __init__(self, rows, *, acquired_at, effective_at, published_at=None, provenance=None, provider_id="synthetic-market_data", vendor="Winner Tilt Synthetic"):
        super().__init__(ProviderMetadata(provider_id, vendor, "market_data"), rows, acquired_at=acquired_at, effective_at=effective_at, published_at=published_at, provenance=provenance)
