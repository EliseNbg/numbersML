"""
Binance REST API client for historical data.

Provides methods for fetching historical trades and klines/candles.
"""

import asyncio
import aiohttp
import time
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class BinanceRESTClient:
    """
    Binance REST API client for historical data.

    Purpose:
        Fetches historical trade data and klines/candles
        from Binance REST API for backfilling gaps.

    API Endpoints:
        - /api/v3/aggTrades: Aggregate trades
        - /api/v3/klines: Kline/candlestick data

    Rate Limits:
        - Weight: 1-5 per request (depends on endpoint)
        - Limit: 1200 weight per minute

    Example:
        >>> client = BinanceRESTClient()
        >>> trades = await client.get_historical_trades(
        ...     symbol='BTCUSDT',
        ...     start_time=datetime.utcnow() - timedelta(hours=1),
        ...     end_time=datetime.now(timezone.utc),
        ... )
    """

    BASE_URL = "https://api.binance.com/api/v3"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        """
        Initialize Binance REST client.

        Args:
            api_key: Binance API key (optional, not needed for public endpoints)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

        # Rate limiting
        self._rate_limiter = RateLimiter(max_weight=1200, window_seconds=60)

        logger.info("BinanceRESTClient initialized")

    async def __aenter__(self) -> 'BinanceRESTClient':
        """Async context manager entry."""
        await self._get_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            headers = {}
            if self.api_key:
                headers['X-MBX-APIKEY'] = self.api_key

            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
        return self._session

    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def get_historical_trades(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Get historical aggregate trades.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            start_time: Start of time range
            end_time: End of time range
            limit: Max trades per request (max: 1000)

        Returns:
            List of trade dictionaries

        Raises:
            BinanceAPIError: If API request fails
        """
        all_trades: List[Dict[str, Any]] = []

        from_id: Optional[int] = None
        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int(end_time.timestamp() * 1000)

        while True:
            # Build request params
            params = {
                'symbol': symbol,
                'startTime': start_ts,
                'endTime': end_ts,
                'limit': limit,
            }

            if from_id is not None:
                params['fromId'] = from_id

            # Make request
            trades = await self._request('GET', '/aggTrades', params)

            if not trades:
                break

            all_trades.extend(trades)

            # Update for next iteration
            from_id = trades[-1]['a']  # Last aggregate trade ID

            # Check if we have more data
            if len(trades) < limit:
                break

            # Rate limiting
            await self._rate_limiter.wait()

        logger.info(
            f"Fetched {len(all_trades)} historical trades for {symbol} "
            f"from {start_time} to {end_time}"
        )

        return all_trades

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Get kline/candlestick data.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            interval: Kline interval (1m, 5m, 1h, etc.)
            start_time: Start of time range
            end_time: End of time range
            limit: Max klines per request (max: 1000)

        Returns:
            List of kline dictionaries

        Raises:
            BinanceAPIError: If API request fails
        """
        all_klines: List[Dict[str, Any]] = []

        current_start = int(start_time.timestamp() * 1000)
        end_ts = int(end_time.timestamp() * 1000)

        while current_start < end_ts:
            # Build request params
            params = {
                'symbol': symbol,
                'interval': interval,
                'startTime': current_start,
                'endTime': end_ts,
                'limit': limit,
            }

            # Make request
            klines = await self._request('GET', '/klines', params)

            if not klines:
                break

            all_klines.extend(klines)

            # Update for next iteration
            # Last kline's close time
            current_start = klines[-1][6] + 1

            # Rate limiting
            await self._rate_limiter.wait()

        logger.info(
            f"Fetched {len(all_klines)} klines for {symbol} "
            f"interval={interval} from {start_time} to {end_time}"
        )

        return all_klines

    async def get_server_time(self) -> datetime:
        """
        Get server time from Binance.

        Returns:
            Server time as datetime

        Raises:
            BinanceAPIError: If API request fails
        """
        data = await self._request('GET', '/time')
        return datetime.fromtimestamp(data['serverTime'] / 1000)

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Make API request.

        Args:
            method: HTTP method
            path: API path
            params: Query parameters

        Returns:
            JSON response

        Raises:
            BinanceAPIError: If request fails
        """
        session = await self._get_session()

        url = f"{self.BASE_URL}{path}"

        # Rate limiting
        await self._rate_limiter.wait()

        async with session.request(method, url, params=params) as response:
            if response.status != 200:
                error_data = await response.json()
                raise BinanceAPIError(
                    f"API error {response.status}: {error_data}"
                )

            return await response.json()


class RateLimiter:
    """
    Rate limiter for Binance API.

    Binance has a weight-based rate limit of 1200 weight per minute.
    """

    def __init__(
        self,
        max_weight: int = 1200,
        window_seconds: int = 60,
    ) -> None:
        """
        Initialize rate limiter.

        Args:
            max_weight: Maximum weight per window
            window_seconds: Time window in seconds
        """
        self.max_weight = max_weight
        self.window_seconds = window_seconds

        self._tokens = float(max_weight)
        self._last_update = time.time()

    async def wait(self, weight: int = 1) -> None:
        """
        Wait until rate limit allows.

        Args:
            weight: Weight of the request
        """
        now = time.time()
        elapsed = now - self._last_update

        # Replenish tokens based on elapsed time
        self._tokens = min(
            self.max_weight,
            self._tokens + elapsed * (self.max_weight / self.window_seconds)
        )
        self._last_update = now

        # Wait if not enough tokens
        if self._tokens < weight:
            wait_time = (weight - self._tokens) / (self.max_weight / self.window_seconds)
            logger.debug(f"Rate limiting: waiting {wait_time:.2f}s")
            await asyncio.sleep(wait_time)
            self._tokens = 0
        else:
            self._tokens -= weight


class BinanceAPIError(Exception):
    """Exception raised for Binance API errors."""

    def __init__(
        self,
        message: str,
        code: Optional[int] = None,
    ) -> None:
        """
        Initialize API error.

        Args:
            message: Error message
            code: Error code if available
        """
        self.message = message
        self.code = code
        super().__init__(self.message)


def parse_trade_data(trade: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse aggregate trade data from Binance.

    Args:
        trade: Raw trade data from API

    Returns:
        Parsed trade dictionary
    """
    return {
        'trade_id': str(trade['a']),  # Aggregate trade ID
        'price': Decimal(trade['p']),
        'quantity': Decimal(trade['q']),
        'time': datetime.fromtimestamp(trade['T'] / 1000),
        'is_buyer_maker': trade['m'],
        'side': 'SELL' if trade['m'] else 'BUY',
    }


def parse_kline_data(kline: List[Any]) -> Dict[str, Any]:
    """
    Parse kline data from Binance.

    Args:
        kline: Raw kline data [open_time, open, high, low, close, volume, ...]

    Returns:
        Parsed kline dictionary
    """
    return {
        'open_time': datetime.fromtimestamp(kline[0] / 1000),
        'close_time': datetime.fromtimestamp(kline[6] / 1000),
        'open': Decimal(kline[1]),
        'high': Decimal(kline[2]),
        'low': Decimal(kline[3]),
        'close': Decimal(kline[4]),
        'volume': Decimal(kline[5]),
        'quote_volume': Decimal(kline[7]),
        'trades_count': kline[8],
    }
