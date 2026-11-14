"""Actual quote provenance for the new format, without acquiring a client to browse."""

from dataclasses import dataclass

from src.config import OddsProviderName, settings
from src.services.betfair import Betfair, FakeBetfair
from src.services.odds_api import OddsApiProvider
from src.services.odds_cache import CachingOddsProvider
from src.services.odds_provider import OddsProvider, OddsProviderAPIError


@dataclass(frozen=True)
class ProviderIdentity:
    source: str
    bookmaker: str

    def __post_init__(self) -> None:
        if (
            not self.source
            or len(self.source) > 40
            or not self.bookmaker
            or len(self.bookmaker) > 80
        ):
            raise OddsProviderAPIError("Unsupported quote provenance")


def configured_identity() -> ProviderIdentity:
    if settings.odds_provider == OddsProviderName.betfair:
        return ProviderIdentity("betfair", "Betfair Exchange")
    if settings.odds_provider == OddsProviderName.fake:
        return ProviderIdentity("fake", "Fake")
    return ProviderIdentity("oddsapi", settings.odds_api_bookmaker)


def native_identity(provider: OddsProvider) -> ProviderIdentity:
    while isinstance(provider, CachingOddsProvider):
        provider = provider.inner
    if isinstance(provider, OddsApiProvider):
        return ProviderIdentity("oddsapi", provider.bookmaker)
    if isinstance(provider, Betfair):
        return ProviderIdentity("betfair", "Betfair Exchange")
    if isinstance(provider, FakeBetfair):
        return ProviderIdentity("fake", "Fake")
    raise OddsProviderAPIError("Unsupported quote provider")


async def acquire_matching(expected: ProviderIdentity) -> OddsProvider:
    from src.services.odds_session import odds_session

    provider = await odds_session.acquire()
    if native_identity(provider) != expected:
        raise OddsProviderAPIError("The current quote provider does not match its provenance")
    return provider
