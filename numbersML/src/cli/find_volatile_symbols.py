#!/usr/bin/env python3
"""
Find the 5 most volatile symbols on Binance.

Fetches 24hr ticker data and calculates volatility.
"""

import asyncio
import aiohttp
from typing import List, Dict, Any
from decimal import Decimal


async def get_most_volatile_symbols(limit: int = 5) -> List[str]:
    """
    Get the most volatile symbols from Binance 24hr ticker.

    Volatility is calculated as: (high - low) / open * 100

    Args:
        limit: Number of symbols to return

    Returns:
        List of symbol strings (e.g., ['BTC/USDT', 'ETH/USDT'])
    """
    url = "https://api.binance.com/api/v3/ticker/24hr"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"API error: {response.status}")

            data = await response.json()

    # Filter and calculate volatility
    symbols_with_volatility: List[Dict[str, Any]] = []

    for ticker in data:
        # Skip non-USDT/USDC pairs for simplicity
        quote_asset = ticker['symbol'][-4:]
        if quote_asset not in ['USDT', 'USDC']:
            continue

        # Skip stablecoins
        base_asset = ticker['symbol'][:-4]
        if base_asset in ['USDT', 'USDC', 'BUSD', 'TUSD', 'DAI', 'FDUSD']:
            continue

        # Calculate volatility
        try:
            high = Decimal(ticker['highPrice'])
            low = Decimal(ticker['lowPrice'])
            open_price = Decimal(ticker['openPrice'])

            if open_price > 0:
                volatility = ((high - low) / open_price) * 100
            else:
                volatility = Decimal('0')

            symbols_with_volatility.append({
                'symbol': f"{base_asset}/{quote_asset}",
                'binance_symbol': ticker['symbol'],
                'volatility': float(volatility),
                'price': ticker['lastPrice'],
                'volume': ticker['volume'],
            })

        except Exception as e:
            continue

    # Sort by volatility (highest first)
    symbols_with_volatility.sort(key=lambda x: x['volatility'], reverse=True)

    # Return top N
    return symbols_with_volatility[:limit]


async def main() -> None:
    """Main entry point."""
    print("Fetching 24hr ticker data from Binance...")
    print("Calculating volatility for all symbols...\n")

    volatile_symbols = await get_most_volatile_symbols(limit=5)

    print("=" * 70)
    print("TOP 5 MOST VOLATILE SYMBOLS (24hr)")
    print("=" * 70)
    print(f"{'Rank':<5} {'Symbol':<15} {'Volatility':<12} {'Price':<15} {'Volume':<20}")
    print("-" * 70)

    for i, sym in enumerate(volatile_symbols, 1):
        print(f"{i:<5} {sym['symbol']:<15} {sym['volatility']:>8.2f}%     "
              f"${sym['price']:<14} {sym['volume']:<20}")

    print("=" * 70)

    # Print as Python list for config
    print("\nSymbols for configuration:")
    symbols_list = [s['symbol'] for s in volatile_symbols]
    print(f"SYMBOLS = {symbols_list}")
    print("\nUse these symbols in your data collection configuration.")


if __name__ == '__main__':
    asyncio.run(main())
