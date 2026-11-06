"""Tests for USD/BRL Currency Service and Caching (TC-004, TC-005)."""

import pytest
import respx
from httpx import Response

from src.services.currency import CurrencyService


@pytest.mark.asyncio
async def test_tc004_currency_fetch_and_cache():
    """TC-004: Fetches exchange rate on boot and caches for subsequent requests."""
    with respx.mock(base_url="https://economia.awesomeapi.com.br") as mock:
        mock.get("/last/USD-BRL").mock(
            return_value=Response(
                200,
                json={
                    "USDBRL": {
                        "code": "USD",
                        "codein": "BRL",
                        "bid": "5.8250",
                        "create_date": "2026-11-06 18:00:00",
                    }
                },
            )
        )

        service = CurrencyService(api_url="https://economia.awesomeapi.com.br/last/USD-BRL")
        rate = await service.get_usd_brl_rate()
        assert rate == 5.8250

        # Subsequent call should return cached value even if API is stopped
        mock.stop()
        cached_rate = await service.get_usd_brl_rate()
        assert cached_rate == 5.8250


@pytest.mark.asyncio
async def test_tc005_currency_network_failure_fallback():
    """TC-005: When external API fails with 500 or timeout, returns safe fallback rate."""
    with respx.mock(base_url="https://economia.awesomeapi.com.br") as mock:
        mock.get("/last/USD-BRL").mock(return_value=Response(500))

        service = CurrencyService(
            api_url="https://economia.awesomeapi.com.br/last/USD-BRL",
            fallback_rate=5.80,
        )
        rate = await service.get_usd_brl_rate()
        assert rate == 5.80
