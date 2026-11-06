"""USD/BRL Currency Service with caching and resilient fallback (TC-004, TC-005)."""

import time
import httpx
from loguru import logger

from src.config import get_settings


class CurrencyService:
    """Provides USD to BRL exchange rate with in-memory caching and fallback."""

    def __init__(
        self,
        api_url: str | None = None,
        cache_ttl_seconds: int = 86400,  # 24 hours
        fallback_rate: float = 5.80,
    ):
        settings = get_settings()
        self.api_url = api_url or settings.AWESOME_API_URL
        self.cache_ttl_seconds = cache_ttl_seconds
        self.fallback_rate = fallback_rate
        self._cached_rate: float | None = None
        self._last_fetched_timestamp: float = 0.0

    async def get_usd_brl_rate(self) -> float:
        """Returns the current USD to BRL rate, fetching if expired, or using fallback."""
        now = time.time()
        if (
            self._cached_rate is not None
            and (now - self._last_fetched_timestamp) < self.cache_ttl_seconds
        ):
            return self._cached_rate

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.api_url)
                if response.status_code == 200:
                    data = response.json()
                    # AwesomeAPI format: {"USDBRL": {"bid": "5.8250"}}
                    if "USDBRL" in data and "bid" in data["USDBRL"]:
                        rate = float(data["USDBRL"]["bid"])
                        self._cached_rate = rate
                        self._last_fetched_timestamp = now
                        logger.info(f"Currency USD/BRL updated: R$ {rate:.4f}")
                        return rate
                logger.warning(
                    f"Exchange API returned unexpected status {response.status_code}. Using fallback."
                )
        except Exception as exc:
            logger.warning(
                f"Failed to fetch live USD/BRL rate ({exc}). Using safe fallback {self.fallback_rate}."
            )

        if self._cached_rate is not None:
            return self._cached_rate

        return self.fallback_rate


# Global singleton instance
_currency_service: CurrencyService | None = None


def get_currency_service() -> CurrencyService:
    global _currency_service
    if _currency_service is None:
        _currency_service = CurrencyService()
    return _currency_service
