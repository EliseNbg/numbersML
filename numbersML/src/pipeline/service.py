"""
Real-Time Trade Pipeline Service.

Orchestrates the complete pipeline:
1. WebSocket connection to Binance
2. Trade aggregation (1-second candles)
3. Gap recovery via REST API
4. Database persistence
5. Indicator calculation trigger

Usage:
    pipeline = TradePipeline(db_pool=pool, symbols=['BTC/USDT'])
    await pipeline.start()
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

import asyncpg

from src.pipeline.websocket_manager import BinanceWebSocketManager, AggTrade
from src.pipeline.aggregator import MultiSymbolAggregator, TradeAggregation
from src.pipeline.recovery import RecoveryManager
from src.pipeline.database_writer import MultiSymbolDatabaseWriter
from src.pipeline.indicator_calculator import IndicatorCalculator
from src.pipeline.wide_vector_service import WideVectorService

logger = logging.getLogger(__name__)


class TradePipeline:
    """
    Main pipeline service for real-time trade processing.
    
    Features:
        - Multi-symbol support
        - Automatic reconnection
        - Gap recovery
        - Batch database writes
        - Statistics tracking
    
    Example:
        >>> pipeline = TradePipeline(
        ...     db_pool=pool,
        ...     symbols=['BTC/USDT', 'ETH/USDT'],
        ... )
        >>> await pipeline.start()
    """
    
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        symbols: List[str],
    ) -> None:
        """
        Initialize pipeline.
        
        Args:
            db_pool: Database connection pool
            symbols: List of symbols to process
        """
        self.db_pool = db_pool
        self.symbols = symbols
        
        # Components
        self._aggregator = MultiSymbolAggregator(on_candle=self._on_candle)
        self._db_writer = MultiSymbolDatabaseWriter(db_pool)
        self._indicator_calculator = IndicatorCalculator(db_pool)
        self._wide_vector_service = WideVectorService(db_pool)
        self._recovery_managers: Dict[str, RecoveryManager] = {}
        self._ws_manager: Optional[BinanceWebSocketManager] = None
        
        # State
        self._running = False
        self._start_time: Optional[datetime] = None
        
        # Statistics
        self._stats = {
            'trades_processed': 0,
            'candles_written': 0,
            'indicators_calculated': 0,
            'indicator_errors': 0,
            'recovery_events': 0,
            'websocket_errors': 0,
            'database_errors': 0,
        }
    
    async def _on_candle(
        self,
        symbol: str,
        candle: TradeAggregation,
    ) -> None:
        """
        Handle completed candle.
        
        Args:
            symbol: Symbol name
            candle: Completed candle
        """
        try:
            # Write to database
            await self._db_writer.write_candle(symbol, candle)
            self._stats['candles_written'] += 1
            
            # Flush candle to DB so indicator calculator can read it
            await self._db_writer.flush_symbol(symbol)
            
            # Calculate indicators (pass candle directly to avoid DB read timing issues)
            try:
                count = await self._indicator_calculator.calculate_with_candle(
                    symbol=symbol,
                    time=candle.time,
                    open=float(candle.open),
                    high=float(candle.high),
                    low=float(candle.low),
                    close=float(candle.close),
                    volume=float(candle.volume),
                )
                if count > 0:
                    self._stats['indicators_calculated'] += count
            except Exception as e:
                logger.error(f"Error calculating indicators for {symbol}: {e}")
                self._stats['indicator_errors'] += 1
            
        except Exception as e:
            logger.error(f"Error processing candle: {e}")
            self._stats['database_errors'] += 1

    async def _ticker_loop(self) -> None:
        """
        1-second ticker loop.
        
        Fires every second, aligns to second boundaries, and calls
        aggregator.tick_all() to emit one candle per symbol.
        """
        while self._running:
            try:
                # Sleep until next second boundary
                now = datetime.now(timezone.utc)
                next_tick = now.replace(microsecond=0) + timedelta(seconds=1)
                sleep_secs = (next_tick - now).total_seconds()
                await asyncio.sleep(sleep_secs)
                
                if not self._running:
                    break
                
                # Tick all aggregators
                tick_time = datetime.now(timezone.utc).replace(microsecond=0)
                await self._aggregator.tick_all(tick_time)
                
                # Generate wide vector after all candles + indicators are done
                try:
                    candle_time = tick_time - timedelta(seconds=1)
                    result = await self._wide_vector_service.generate(candle_time)
                    if result:
                        self._stats['wide_vectors_generated'] = self._stats.get('wide_vectors_generated', 0) + 1
                        logger.debug(f"Wide vector generated for {candle_time}: {result['vector_size']} features")
                    else:
                        logger.debug(f"Wide vector returned None for {candle_time}")
                except Exception as e:
                    logger.error(f"Wide vector error: {e}")
                    self._stats['wide_vector_errors'] = self._stats.get('wide_vector_errors', 0) + 1
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ticker error: {e}")
    
    async def _on_trade(self, trade: AggTrade) -> None:
        """
        Handle incoming trade.
        
        Args:
            trade: Trade from WebSocket
        """
        try:
            self._stats['trades_processed'] += 1
            
            # Convert symbol format (BTCUSDT -> BTC/USDT)
            symbol = trade.symbol
            if '/' not in symbol:
                # Insert slash before quote asset
                for quote in ['USDT', 'USDC', 'BUSD', 'BTC', 'ETH', 'BNB']:
                    if symbol.endswith(quote):
                        symbol = f"{symbol[:-len(quote)]}/{quote}"
                        break
            
            # Process through recovery manager (gap detection)
            if symbol in self._recovery_managers:
                await self._recovery_managers[symbol].process_trade(trade)
            
            # Aggregate trade
            await self._aggregator.add_trade(symbol, trade)
            
        except Exception as e:
            logger.error(f"Error processing trade: {e}")
            self._stats['websocket_errors'] += 1
    
    async def _initialize_recovery_managers(self) -> None:
        """Initialize recovery managers for all symbols."""
        for symbol in self.symbols:
            recovery = RecoveryManager(
                symbol=symbol,
                db_pool=self.db_pool,
                on_trade=self._on_trade,
            )
            await recovery.initialize()
            self._recovery_managers[symbol] = recovery
            
            logger.info(f"Initialized recovery manager for {symbol}")
    
    async def start(self) -> None:
        """
        Start pipeline.
        
        Connects to WebSocket and starts processing trades.
        """
        if self._running:
            logger.warning("Pipeline already running")
            return
        
        logger.info("Starting trade pipeline")
        self._running = True
        self._start_time = datetime.now(timezone.utc)
        
        # Initialize components
        await self._initialize_recovery_managers()
        await self._db_writer.start()
        await self._indicator_calculator.load_definitions()
        await self._wide_vector_service.load_symbols()
        
        # Create WebSocket manager
        self._ws_manager = BinanceWebSocketManager(
            symbols=self.symbols,
            on_trade=self._on_trade,
        )
        
        # Start 1-second ticker for candle emission
        self._ticker_task = asyncio.create_task(self._ticker_loop())
        
        # Start WebSocket (runs until stopped)
        try:
            await self._ws_manager.start()
        except asyncio.CancelledError:
            logger.info("Pipeline cancelled")
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            self._stats['websocket_errors'] += 1
        finally:
            await self.stop()
    
    async def stop(self) -> None:
        """Stop pipeline gracefully."""
        if not self._running:
            return
        
        logger.info("Stopping trade pipeline")
        self._running = False
        
        # Stop components
        if self._ws_manager:
            await self._ws_manager.stop()
        
        # Stop ticker
        if hasattr(self, '_ticker_task') and self._ticker_task:
            self._ticker_task.cancel()
            try:
                await self._ticker_task
            except asyncio.CancelledError:
                pass
        
        await self._db_writer.stop()
        
        for recovery in self._recovery_managers.values():
            await recovery.close()
        
        # Persist final state
        await self._persist_final_state()
        
        logger.info("Trade pipeline stopped")
    
    async def _persist_final_state(self) -> None:
        """Persist final pipeline state."""
        async with self.db_pool.acquire() as conn:
            for symbol, recovery in self._recovery_managers.items():
                symbol_id = await conn.fetchval(
                    "SELECT id FROM symbols WHERE symbol = $1",
                    symbol,
                )
                
                if symbol_id:
                    stats = recovery.get_stats()
                    uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds() if self._start_time else 0
                    tps = self._stats['trades_processed'] / max(1, uptime)
                    
                    await conn.execute(
                        """
                        INSERT INTO pipeline_metrics (
                            timestamp, symbol_id, symbol,
                            total_time_ms, active_symbols_count,
                            status
                        ) VALUES (NOW(), $1, $2, $3, $4, 'success')
                        """,
                        symbol_id,
                        symbol,
                        int(1000 / max(tps, 0.001)),
                        len(self.symbols),
                    )
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get pipeline status.
        
        Returns:
            Status dictionary
        """
        uptime = 0.0
        if self._start_time:
            uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()
        
        trades_per_second = 0.0
        if uptime > 0:
            trades_per_second = self._stats['trades_processed'] / uptime
        
        return {
            'is_running': self._running,
            'symbols': self.symbols,
            'uptime_seconds': uptime,
            'trades_per_second': trades_per_second,
            'trades_processed': self._stats['trades_processed'],
            'candles_written': self._stats['candles_written'],
            'recovery_events': self._stats['recovery_events'],
            'websocket_errors': self._stats['websocket_errors'],
            'database_errors': self._stats['database_errors'],
        }
    
    def get_detailed_stats(self) -> Dict[str, Any]:
        """
        Get detailed statistics.
        
        Returns:
            Detailed statistics dictionary
        """
        stats = {
            'pipeline': self.get_status(),
            'aggregator': self._aggregator.get_stats(),
            'database_writer': self._db_writer.get_stats(),
            'recovery': {},
        }
        
        for symbol, recovery in self._recovery_managers.items():
            stats['recovery'][symbol] = recovery.get_stats()
        
        if self._ws_manager:
            stats['websocket'] = self._ws_manager.get_stats()
        
        return stats


class PipelineManager:
    """
    Manager for multiple pipeline instances.
    
    Allows starting/stopping pipelines for different symbol sets.
    
    Example:
        >>> manager = PipelineManager(db_pool=pool)
        >>> await manager.start_pipeline(symbols=['BTC/USDT', 'ETH/USDT'])
        >>> status = manager.get_pipeline_status()
    """
    
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """
        Initialize pipeline manager.
        
        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool
        self._pipelines: Dict[str, TradePipeline] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
    
    async def start_pipeline(self, symbols: List[str], pipeline_id: str = 'default') -> bool:
        """
        Start pipeline for symbols.
        
        Args:
            symbols: List of symbols to process
            pipeline_id: Unique pipeline identifier
        
        Returns:
            True if started successfully
        """
        if pipeline_id in self._pipelines:
            # Check if existing task is still running
            task = self._tasks.get(pipeline_id)
            if task and not task.done():
                logger.warning(f"Pipeline {pipeline_id} already running")
                return False
            # Clean up stale pipeline
            logger.info(f"Cleaning up stale pipeline {pipeline_id}")
            del self._pipelines[pipeline_id]
            if pipeline_id in self._tasks:
                del self._tasks[pipeline_id]
        
        # Get active symbols from database
        async with self.db_pool.acquire() as conn:
            if symbols:
                rows = await conn.fetch(
                    """
                    SELECT symbol FROM symbols
                    WHERE is_active = true AND is_allowed = true AND symbol = ANY($1)
                    """,
                    symbols,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT symbol FROM symbols
                    WHERE is_active = true AND is_allowed = true
                    ORDER BY symbol
                    """
                )
            active_symbols = [row['symbol'] for row in rows]
        
        if not active_symbols:
            logger.warning("No active symbols for pipeline")
            return False
        
        # Create and start pipeline
        pipeline = TradePipeline(
            db_pool=self.db_pool,
            symbols=active_symbols,
        )
        
        task = asyncio.create_task(pipeline.start())
        
        def _task_done(t: asyncio.Task) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error(f"Pipeline {pipeline_id} task failed: {exc}")
        
        task.add_done_callback(_task_done)
        
        self._pipelines[pipeline_id] = pipeline
        self._tasks[pipeline_id] = task
        
        logger.info(f"Started pipeline {pipeline_id} with {len(active_symbols)} symbols")
        return True
    
    async def stop_pipeline(self, pipeline_id: str) -> bool:
        """
        Stop pipeline.
        
        Args:
            pipeline_id: Pipeline identifier
        
        Returns:
            True if stopped successfully
        """
        if pipeline_id not in self._pipelines:
            return False
        
        pipeline = self._pipelines[pipeline_id]
        
        try:
            await pipeline.stop()
        except Exception as e:
            logger.error(f"Error stopping pipeline {pipeline_id}: {e}")
        
        if pipeline_id in self._tasks:
            self._tasks[pipeline_id].cancel()
            try:
                await self._tasks[pipeline_id]
            except (asyncio.CancelledError, Exception):
                pass
        
        self._pipelines.pop(pipeline_id, None)
        self._tasks.pop(pipeline_id, None)
        
        logger.info(f"Stopped pipeline {pipeline_id}")
        return True
    
    def get_pipeline_status(self, pipeline_id: str = 'default') -> Optional[Dict[str, Any]]:
        """
        Get pipeline status.
        
        Args:
            pipeline_id: Pipeline identifier
        
        Returns:
            Status dictionary or None if not found
        """
        if pipeline_id not in self._pipelines:
            return None
        
        return self._pipelines[pipeline_id].get_status()
    
    def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status for all pipelines.
        
        Returns:
            Dictionary of pipeline statuses
        """
        return {
            pid: pipeline.get_status()
            for pid, pipeline in self._pipelines.items()
        }
    
    async def stop_all(self) -> None:
        """Stop all pipelines."""
        for pipeline_id in list(self._pipelines.keys()):
            await self.stop_pipeline(pipeline_id)
        
        logger.info("All pipelines stopped")


# Global pipeline manager instance (for API dependency injection)
_pipeline_manager = None


def get_pipeline_manager() -> Optional[PipelineManager]:
    """Get global pipeline manager instance."""
    return _pipeline_manager


def set_pipeline_manager(manager: PipelineManager) -> None:
    """Set global pipeline manager instance."""
    global _pipeline_manager
    _pipeline_manager = manager
