"""
Recovery Manager for gap detection and trade recovery via REST API.

Features:
- Gap detection (missing trade IDs)
- REST API client for fetching missing trades
- State persistence in database
- Automatic recovery on reconnection

Binance REST API:
    GET /api/v3/aggTrades
    
    Parameters:
        - symbol: BTCUSDT
        - fromId: Start trade ID
        - startTime: Start time (ms)
        - endTime: End time (ms)
        - limit: Max 1000

Usage:
    recovery = RecoveryManager(symbol='BTC/USDT', db_pool=pool)
    await recovery.recover_missing_trades(last_trade_id=12345)
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import asyncio

import aiohttp
import asyncpg

from src.pipeline.websocket_manager import AggTrade

logger = logging.getLogger(__name__)


class BinanceRESTClient:
    """
    Binance REST API client for trade recovery.
    
    Endpoints:
        - /api/v3/aggTrades: Aggregate trades
    
    Example:
        >>> client = BinanceRESTClient()
        >>> trades = await client.get_agg_trades(
        ...     symbol='BTCUSDT',
        ...     fromId=12345,
        ...     limit=1000,
        ... )
    """
    
    BASE_URL = "https://api.binance.com/api/v3"
    
    def __init__(self) -> None:
        """Initialize REST client."""
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def get_agg_trades(
        self,
        symbol: str,
        from_id: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[AggTrade]:
        """
        Fetch aggregate trades from REST API.
        
        Args:
            symbol: Symbol (e.g., 'BTCUSDT')
            from_id: Start from trade ID
            start_time: Start time
            end_time: End time
            limit: Max trades to fetch (max 1000)
        
        Returns:
            List of AggTrade objects
        """
        session = await self._get_session()
        
        params = {
            'symbol': symbol,
            'limit': min(limit, 1000),
        }
        
        # Binance API: fromId cannot be combined with startTime/endTime
        if from_id is not None:
            params['fromId'] = from_id
        elif start_time is not None and end_time is not None:
            params['startTime'] = int(start_time.timestamp() * 1000)
            params['endTime'] = int(end_time.timestamp() * 1000)
        
        url = f"{self.BASE_URL}/aggTrades"
        
        try:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"REST API error: {error_text}")
                    return []
                
                data = await response.json()
                
                # Parse trades
                trades = []
                for trade_data in data:
                    trade = AggTrade(
                        event_type='aggTrade',
                        event_time=trade_data.get('E', 0),
                        symbol=trade_data.get('s', symbol),
                        agg_trade_id=trade_data['a'],
                        price=Decimal(trade_data['p']),
                        quantity=Decimal(trade_data['q']),
                        first_trade_id=trade_data['f'],
                        last_trade_id=trade_data['l'],
                        trade_time=trade_data['T'],
                        is_buyer_maker=trade_data['m'],
                    )
                    trades.append(trade)
                
                logger.info(f"Fetched {len(trades)} trades from REST API")
                return trades
                
        except Exception as e:
            logger.error(f"Failed to fetch trades from REST: {e}")
            return []


class RecoveryManager:
    """
    Manager for gap detection and trade recovery.
    
    Features:
        - Track last processed trade ID
        - Detect gaps in trade sequence
        - Fetch missing trades via REST API
        - Persist state in database
    
    Example:
        >>> recovery = RecoveryManager(symbol='BTC/USDT', db_pool=pool)
        >>> await recovery.initialize()
        >>> 
        >>> # On trade received
        >>> await recovery.process_trade(trade)
        >>> 
        >>> # On reconnection
        >>> await recovery.recover_missing_trades()
    """
    
    # Recovery settings
    MAX_RECOVERY_WINDOW = timedelta(minutes=5)
    MAX_TRADES_PER_RECOVERY = 10000
    
    def __init__(
        self,
        symbol: str,
        db_pool: asyncpg.Pool,
        on_trade: Callable,
    ) -> None:
        """
        Initialize recovery manager.
        
        Args:
            symbol: Symbol (e.g., 'BTC/USDT')
            db_pool: Database connection pool
            on_trade: Callback for recovered trades
        """
        self.symbol = symbol
        self.db_pool = db_pool
        self.on_trade = on_trade
        
        # State
        self._last_trade_id: int = 0
        self._last_timestamp: datetime = datetime.now(timezone.utc)
        self._is_recovering: bool = False
        self._rest_client = BinanceRESTClient()
        
        # Statistics
        self._stats = {
            'gaps_detected': 0,
            'trades_recovered': 0,
            'recovery_events': 0,
            'last_recovery_time': None,
            '_last_persisted_gaps': 0,
            '_last_persisted_trades': 0,
        }
    
    async def initialize(self) -> None:
        """
        Initialize recovery state from database.
        """
        async with self.db_pool.acquire() as conn:
            # Get symbol ID
            symbol_id = await conn.fetchval(
                "SELECT id FROM symbols WHERE symbol = $1",
                self.symbol,
            )
            
            if not symbol_id:
                logger.error(f"Symbol {self.symbol} not found in database")
                return
            
            # Load state
            row = await conn.fetchrow(
                """
                SELECT last_trade_id, last_timestamp, is_recovering,
                       gaps_detected, trades_processed
                FROM pipeline_state
                WHERE symbol_id = $1
                """,
                symbol_id,
            )
            
            if row:
                self._last_trade_id = row['last_trade_id'] or 0
                ts = row['last_timestamp']
                self._last_timestamp = ts.replace(tzinfo=timezone.utc) if ts else datetime.now(timezone.utc)
                self._is_recovering = row['is_recovering'] or False
                self._stats['gaps_detected'] = row['gaps_detected'] or 0
            
            logger.info(
                f"Recovery initialized for {self.symbol}: "
                f"last_trade_id={self._last_trade_id}"
            )
    
    async def process_trade(self, trade: AggTrade) -> bool:
        """
        Process incoming trade and check for gaps.

        Always passes the trade to the aggregator (for candle generation).
        If a gap is detected, recovers missing trades synchronously first.

        Args:
            trade: Trade to process

        Returns:
            True if trade was processed
        """
        # Check for gap
        if self._last_trade_id > 0 and trade.agg_trade_id > self._last_trade_id + 1:
            expected_id = self._last_trade_id + 1
            gap_size = trade.agg_trade_id - expected_id
            logger.warning(
                f"Gap detected for {self.symbol}: "
                f"expected {expected_id}, got {trade.agg_trade_id} "
                f"(gap: {gap_size} trades)"
            )
            self._stats['gaps_detected'] += 1

            # Recover missing trades synchronously (blocks until done)
            # Recovery calls on_trade → aggregator for each recovered trade
            await self._recover_gap(
                from_id=expected_id,
                to_id=trade.agg_trade_id - 1,
            )

        # Update state
        self._last_trade_id = trade.agg_trade_id
        self._last_timestamp = trade.timestamp

        # Persist state periodically (every 100 trades)
        if self._last_trade_id % 100 == 0:
            await self._persist_state()

        # Always pass trade to on_trade → aggregator
        # This ensures the aggregator always has the latest data
        # for candle generation, regardless of recovery state
        await self.on_trade(trade)

        return True

    async def _recover_gap(
        self,
        from_id: int,
        to_id: int,
    ) -> None:
        """
        Recover missing trades via REST API.

        Loops in batches until the full gap is closed.

        Args:
            from_id: Start trade ID
            to_id: End trade ID
        """
        self._is_recovering = True
        self._stats['recovery_events'] += 1
        self._stats['last_recovery_time'] = datetime.now(timezone.utc)

        gap_size = to_id - from_id + 1
        logger.info(f"Starting recovery for {self.symbol}: {from_id} to {to_id} ({gap_size} trades)")

        total_recovered = 0
        current_from = from_id

        try:
            while current_from <= to_id:
                # Calculate time window for this batch
                end_time = datetime.now(timezone.utc)
                start_time = end_time - self.MAX_RECOVERY_WINDOW

                # Fetch missing trades
                trades = await self._rest_client.get_agg_trades(
                    symbol=self.symbol.replace('/', ''),
                    from_id=current_from,
                    start_time=start_time,
                    end_time=end_time,
                    limit=self.MAX_TRADES_PER_RECOVERY,
                )

                if not trades:
                    logger.warning(f"No more trades returned from REST API at fromId={current_from}")
                    break

                # Process recovered trades
                batch_count = 0
                for trade in trades:
                    if trade.agg_trade_id > to_id:
                        break
                    self._last_trade_id = trade.agg_trade_id
                    self._last_timestamp = trade.timestamp
                    await self.on_trade(trade)
                    self._stats['trades_recovered'] += 1
                    total_recovered += 1
                    batch_count += 1

                # Advance to next batch
                last_id_in_batch = trades[-1].agg_trade_id
                if last_id_in_batch < current_from:
                    # No progress, avoid infinite loop
                    logger.warning(f"No progress in recovery: last_id={last_id_in_batch} < from={current_from}")
                    break
                current_from = last_id_in_batch + 1

                logger.info(
                    f"Recovery batch: {batch_count} trades processed, "
                    f"{total_recovered}/{gap_size} total, "
                    f"next fromId={current_from}"
                )

                # Yield control to allow other tasks (candle processing) to run
                await asyncio.sleep(0)

            logger.info(f"Recovery complete for {self.symbol}: {total_recovered} trades recovered")

        except Exception as e:
            logger.error(f"Recovery failed for {self.symbol}: {e}")

        finally:
            self._is_recovering = False
            await self._persist_state()
    
    async def recover_missing_trades(self) -> int:
        """
        Recover trades since last known trade ID.
        
        Call this on reconnection after WebSocket disconnect.
        
        Returns:
            Number of trades recovered
        """
        if self._last_trade_id == 0:
            logger.info("No previous trade ID, skipping recovery")
            return 0
        
        # Calculate time window
        end_time = datetime.now(timezone.utc)
        start_time = self._last_timestamp
        
        # Limit recovery window
        if end_time - start_time > self.MAX_RECOVERY_WINDOW:
            start_time = end_time - self.MAX_RECOVERY_WINDOW
        
        logger.info(
            f"Recovering trades for {self.symbol} "
            f"from {start_time} to {end_time}"
        )
        
        trades = await self._rest_client.get_agg_trades(
            symbol=self.symbol.replace('/', ''),
            from_id=self._last_trade_id + 1,
            start_time=start_time,
            end_time=end_time,
            limit=self.MAX_TRADES_PER_RECOVERY,
        )
        
        # Process recovered trades
        for trade in trades:
            await self.on_trade(trade)
            self._stats['trades_recovered'] += 1
        
        logger.info(f"Recovered {len(trades)} trades")
        return len(trades)
    
    async def _persist_state(self) -> None:
        """Persist current state to database."""
        async with self.db_pool.acquire() as conn:
            # Get symbol ID
            symbol_id = await conn.fetchval(
                "SELECT id FROM symbols WHERE symbol = $1",
                self.symbol,
            )
            
            if not symbol_id:
                return
            
            # Update state
            gaps = self._stats['gaps_detected'] - self._stats['_last_persisted_gaps']
            trades = self._stats['trades_recovered'] - self._stats['_last_persisted_trades']
            
            await conn.execute(
                """
                INSERT INTO pipeline_state (
                    symbol_id, last_trade_id, last_timestamp,
                    is_recovering, recovery_start_time,
                    gaps_detected, trades_processed, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                ON CONFLICT (symbol_id) DO UPDATE SET
                    last_trade_id = EXCLUDED.last_trade_id,
                    last_timestamp = EXCLUDED.last_timestamp,
                    is_recovering = EXCLUDED.is_recovering,
                    gaps_detected = pipeline_state.gaps_detected + EXCLUDED.gaps_detected,
                    trades_processed = pipeline_state.trades_processed + EXCLUDED.trades_processed,
                    updated_at = NOW()
                """,
                symbol_id,
                self._last_trade_id,
                self._last_timestamp,
                self._is_recovering,
                self._stats['last_recovery_time'] if (self._is_recovering and self._stats['last_recovery_time']) else None,
                gaps,
                trades,
            )
            
            self._stats['_last_persisted_gaps'] = self._stats['gaps_detected']
            self._stats['_last_persisted_trades'] = self._stats['trades_recovered']
    
    async def close(self) -> None:
        """Close recovery manager."""
        await self._persist_state()
        await self._rest_client.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get recovery statistics.
        
        Returns:
            Dictionary with statistics
        """
        return {
            'symbol': self.symbol,
            'last_trade_id': self._last_trade_id,
            'last_timestamp': self._last_timestamp.isoformat(),
            'is_recovering': self._is_recovering,
            **self._stats,
        }
