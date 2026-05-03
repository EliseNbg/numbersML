"""
Binance WebSocket Manager for aggTrade streams.

Handles:
- WebSocket connection management
- Automatic reconnection with exponential backoff
- Message parsing and validation
- Error handling and logging

Usage:
    manager = BinanceWebSocketManager(symbols=['BTC/USDT', 'ETH/USDT'])
    await manager.start()
"""

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Optional

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

logger = logging.getLogger(__name__)


@dataclass
class AggTrade:
    """
    Aggregate trade from Binance WebSocket.

    Attributes:
        event_type: Event type (always 'aggTrade')
        event_time: Event timestamp (ms)
        symbol: Symbol (e.g., 'BTCUSDT')
        agg_trade_id: Aggregate trade ID
        price: Trade price
        quantity: Trade quantity
        first_trade_id: First trade ID in this aggregate
        last_trade_id: Last trade ID in this aggregate
        trade_time: Trade timestamp (ms)
        is_buyer_maker: True if buyer is maker
    """

    event_type: str
    event_time: int
    symbol: str
    agg_trade_id: int
    price: Decimal
    quantity: Decimal
    first_trade_id: int
    last_trade_id: int
    trade_time: int
    is_buyer_maker: bool

    @property
    def timestamp(self) -> datetime:
        """Convert trade_time to datetime."""
        return datetime.fromtimestamp(self.trade_time / 1000, tz=UTC)

    @property
    def quote_quantity(self) -> Decimal:
        """Calculate quote quantity (price * quantity)."""
        return self.price * self.quantity

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            **asdict(self),
            "timestamp": self.timestamp.isoformat(),
            "quote_quantity": str(self.quote_quantity),
        }


class BinanceWebSocketManager:
    """
    Manager for Binance WebSocket aggTrade streams.

    Features:
        - Connect to multiple symbol streams
        - Automatic reconnection with exponential backoff
        - Message validation
        - Error handling and logging

    Example:
        >>> async def on_trade(trade: AggTrade):
        ...     print(f"Trade: {trade.symbol} @ {trade.price}")
        >>>
        >>> manager = BinanceWebSocketManager(
        ...     symbols=['BTC/USDT', 'ETH/USDT'],
        ...     on_trade=on_trade,
        ... )
        >>> await manager.start()
    """

    # Binance WebSocket endpoints
    WS_BASE_URL = "wss://stream.binance.com:9443/ws"
    WS_COMBINED_URL = "wss://stream.binance.com:9443/stream?streams="

    # Reconnection settings
    INITIAL_RECONNECT_DELAY = 1.0  # seconds
    MAX_RECONNECT_DELAY = 60.0  # seconds
    RECONNECT_MULTIPLIER = 2.0

    def __init__(
        self,
        symbols: list[str],
        on_trade: Callable[[AggTrade], None],
        use_combined_stream: bool = True,
    ) -> None:
        """
        Initialize WebSocket manager.

        Args:
            symbols: List of symbols (e.g., ['BTC/USDT', 'ETH/USDT'])
            on_trade: Callback function for each trade
            use_combined_stream: Use combined stream for multiple symbols
        """
        self.symbols = symbols
        self.on_trade = on_trade
        self.use_combined_stream = use_combined_stream

        # State
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._reconnect_delay = self.INITIAL_RECONNECT_DELAY
        self._stats = {
            "trades_received": 0,
            "errors": 0,
            "reconnections": 0,
            "start_time": None,
        }

    def _get_ws_url(self) -> str:
        """
        Get WebSocket URL for configured symbols.

        Returns:
            WebSocket URL string
        """
        if len(self.symbols) == 1 and not self.use_combined_stream:
            # Single stream
            symbol_lower = self.symbols[0].replace("/", "").lower()
            return f"{self.WS_BASE_URL}/{symbol_lower}@aggTrade"
        else:
            # Combined stream
            streams = "/".join(f"{s.replace('/', '').lower()}@aggTrade" for s in self.symbols)
            return f"{self.WS_COMBINED_URL}{streams}"

    def _parse_message(self, message: str) -> Optional[AggTrade]:
        """
        Parse WebSocket message into AggTrade.

        Args:
            message: Raw WebSocket message

        Returns:
            AggTrade object or None if invalid
        """
        try:
            data = json.loads(message)

            # Handle combined stream format
            if "stream" in data and "data" in data:
                data = data["data"]

            # Validate required fields
            required_fields = ["a", "p", "q", "f", "l", "T", "m"]
            if not all(field in data for field in required_fields):
                logger.warning(f"Missing fields in message: {data.keys()}")
                return None

            # Parse trade
            trade = AggTrade(
                event_type=data.get("e", "aggTrade"),
                event_time=data.get("E", 0),
                symbol=data.get("s", ""),
                agg_trade_id=data["a"],
                price=Decimal(data["p"]),
                quantity=Decimal(data["q"]),
                first_trade_id=data["f"],
                last_trade_id=data["l"],
                trade_time=data["T"],
                is_buyer_maker=data["m"],
            )

            return trade

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse message: {e}")
            self._stats["errors"] += 1
            return None

    async def _connect(self) -> None:
        """
        Establish WebSocket connection.

        Raises:
            WebSocketException: If connection fails
        """
        url = self._get_ws_url()
        logger.info(f"Connecting to Binance WebSocket: {url}")

        self._ws = await websockets.connect(
            url,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=5,
        )

        logger.info("WebSocket connected successfully")

    async def _reconnect(self) -> None:
        """
        Reconnect with exponential backoff.
        """
        while self._running:
            try:
                logger.info(
                    f"Reconnecting in {self._reconnect_delay:.1f}s "
                    f"(attempt {self._stats['reconnections'] + 1})"
                )
                await asyncio.sleep(self._reconnect_delay)

                # Increase delay for next attempt
                self._reconnect_delay = min(
                    self._reconnect_delay * self.RECONNECT_MULTIPLIER,
                    self.MAX_RECONNECT_DELAY,
                )

                await self._connect()

                # Reset delay on successful connection
                self._reconnect_delay = self.INITIAL_RECONNECT_DELAY
                self._stats["reconnections"] += 1

                logger.info("Reconnection successful")
                return

            except Exception as e:
                logger.error(f"Reconnection failed: {e}")
                self._stats["errors"] += 1

    async def _process_message(self, message: str) -> None:
        """
        Process incoming WebSocket message.

        Args:
            message: Raw WebSocket message
        """
        trade = self._parse_message(message)

        if trade:
            self._stats["trades_received"] += 1
            await self.on_trade(trade)

    async def _message_loop(self) -> None:
        """
        Main message processing loop.
        """
        try:
            async for message in self._ws:
                if not self._running:
                    break

                try:
                    await self._process_message(message)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    self._stats["errors"] += 1

        except ConnectionClosed as e:
            logger.warning(f"WebSocket connection closed: {e}")
            raise
        except WebSocketException as e:
            logger.error(f"WebSocket error: {e}")
            self._stats["errors"] += 1
            raise

    async def start(self) -> None:
        """
        Start WebSocket manager.

        Connects to Binance WebSocket and starts processing trades.
        Reconnects automatically on connection loss.
        """
        logger.info("Starting Binance WebSocket Manager")
        self._running = True
        self._stats["start_time"] = datetime.now(UTC)

        while self._running:
            try:
                # Connect
                await self._connect()

                # Process messages
                await self._message_loop()

            except Exception as e:
                if self._running:
                    logger.error(f"Connection error: {e}")
                    self._stats["errors"] += 1

                    # Reconnect
                    await self._reconnect()
                else:
                    logger.info("WebSocket manager stopped")
                    break

    async def stop(self) -> None:
        """
        Stop WebSocket manager gracefully.
        """
        logger.info("Stopping Binance WebSocket Manager")
        self._running = False

        if self._ws:
            await self._ws.close()

        logger.info("WebSocket manager stopped")

    def get_stats(self) -> dict[str, Any]:
        """
        Get manager statistics.

        Returns:
            Dictionary with statistics
        """
        stats = self._stats.copy()

        if stats["start_time"]:
            uptime = (datetime.now(UTC) - stats["start_time"]).total_seconds()
            stats["uptime_seconds"] = uptime

            if uptime > 0:
                stats["trades_per_second"] = stats["trades_received"] / uptime

        return stats
