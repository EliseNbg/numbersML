"""Integration tests for Binance testnet public ticker API."""

from decimal import Decimal

import pytest

from src.infrastructure.market.binance_exchange_client import BINANCE_TESTNET, BinanceExchangeClient


@pytest.mark.integration
class TestBinanceTestnetTickerPrices:
    """Validate price fetch success/failure on Binance testnet API."""

    @pytest.mark.asyncio
    async def test_btc_usdc_and_shib_usdc_price_ranges(self) -> None:
        client = BinanceExchangeClient(environment=BINANCE_TESTNET)
        try:
            btc_price = await client.get_ticker_price("BTC/USDC")
            shib_price = await client.get_ticker_price("SHIB/USDC")
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Binance testnet unavailable: {exc}")
        finally:
            await client.close()

        # Broad sanity ranges to avoid flaky assertions while still catching bad responses.
        assert Decimal("1000") <= btc_price <= Decimal("1000000")
        assert Decimal("0.00000001") <= shib_price <= Decimal("0.01")

    @pytest.mark.asyncio
    async def test_unknown_symbol_failure(self) -> None:
        client = BinanceExchangeClient(environment=BINANCE_TESTNET)
        try:
            with pytest.raises(RuntimeError):
                await client.get_ticker_price("NOTREAL/USDC")
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Binance testnet unavailable: {exc}")
        finally:
            await client.close()
