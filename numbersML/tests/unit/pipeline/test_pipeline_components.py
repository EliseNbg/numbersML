"""
Unit tests for real-time trade pipeline components.

Tests:
- WebSocket manager
- Trade aggregator
- Recovery manager
- Database writer
"""

import pytest
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.pipeline.websocket_manager import AggTrade, BinanceWebSocketManager
from src.pipeline.aggregator import TradeAggregation, MultiSymbolAggregator
from src.pipeline.database_writer import DatabaseWriter


class TestAggTrade:
    """Test AggTrade dataclass."""
    
    def test_create_trade(self) -> None:
        """Test creating trade."""
        trade = AggTrade(
            event_type='aggTrade',
            event_time=123456789,
            symbol='BTCUSDT',
            agg_trade_id=12345,
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            first_trade_id=100,
            last_trade_id=105,
            trade_time=123456789,
            is_buyer_maker=False,
        )
        
        assert trade.agg_trade_id == 12345
        assert trade.price == Decimal('50000.00')
        assert trade.quantity == Decimal('0.001')
    
    def test_quote_quantity(self) -> None:
        """Test quote quantity calculation."""
        trade = AggTrade(
            event_type='aggTrade',
            event_time=123456789,
            symbol='BTCUSDT',
            agg_trade_id=12345,
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            first_trade_id=100,
            last_trade_id=105,
            trade_time=123456789,
            is_buyer_maker=False,
        )
        
        assert trade.quote_quantity == Decimal('50.00')
    
    def test_timestamp(self) -> None:
        """Test timestamp conversion."""
        trade = AggTrade(
            event_type='aggTrade',
            event_time=123456789000,
            symbol='BTCUSDT',
            agg_trade_id=12345,
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            first_trade_id=100,
            last_trade_id=105,
            trade_time=123456789000,
            is_buyer_maker=False,
        )
        
        ts = trade.timestamp
        assert ts.year == 1973  # 123456789000 ms = 1973-11-29
        assert ts.tzinfo == timezone.utc


class TestTradeAggregation:
    """Test TradeAggregation dataclass."""
    
    def test_create_aggregation(self) -> None:
        """Test creating aggregation."""
        time = datetime.now(timezone.utc)
        agg = TradeAggregation(
            time=time,
            symbol='BTC/USDT',
        )
        
        assert agg.time == time
        assert agg.symbol == 'BTC/USDT'
        assert agg.trade_count == 0
    
    def test_update_first_trade(self) -> None:
        """Test updating with first trade."""
        time = datetime.now(timezone.utc)
        agg = TradeAggregation(
            time=time,
            symbol='BTC/USDT',
        )
        
        trade = AggTrade(
            event_type='aggTrade',
            event_time=123456789,
            symbol='BTCUSDT',
            agg_trade_id=12345,
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            first_trade_id=100,
            last_trade_id=105,
            trade_time=123456789,
            is_buyer_maker=False,
        )
        
        agg.update(trade)
        
        assert agg.open == Decimal('50000.00')
        assert agg.high == Decimal('50000.00')
        assert agg.low == Decimal('50000.00')
        assert agg.close == Decimal('50000.00')
        assert agg.volume == Decimal('0.001')
        assert agg.trade_count == 1
    
    def test_update_multiple_trades(self) -> None:
        """Test updating with multiple trades."""
        time = datetime.now(timezone.utc)
        agg = TradeAggregation(
            time=time,
            symbol='BTC/USDT',
        )
        
        # First trade
        trade1 = AggTrade(
            event_type='aggTrade',
            event_time=123456789,
            symbol='BTCUSDT',
            agg_trade_id=12345,
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            first_trade_id=100,
            last_trade_id=105,
            trade_time=123456789,
            is_buyer_maker=False,
        )
        agg.update(trade1)
        
        # Second trade (higher price)
        trade2 = AggTrade(
            event_type='aggTrade',
            event_time=123456790,
            symbol='BTCUSDT',
            agg_trade_id=12346,
            price=Decimal('51000.00'),
            quantity=Decimal('0.002'),
            first_trade_id=106,
            last_trade_id=110,
            trade_time=123456790,
            is_buyer_maker=False,
        )
        agg.update(trade2)
        
        assert agg.open == Decimal('50000.00')
        assert agg.high == Decimal('51000.00')
        assert agg.low == Decimal('50000.00')
        assert agg.close == Decimal('51000.00')
        assert agg.volume == Decimal('0.003')
        assert agg.trade_count == 2
    
    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        time = datetime.now(timezone.utc)
        agg = TradeAggregation(
            time=time,
            symbol='BTC/USDT',
            open=Decimal('50000.00'),
            high=Decimal('51000.00'),
            low=Decimal('49000.00'),
            close=Decimal('50500.00'),
            volume=Decimal('1.0'),
            quote_volume=Decimal('50000.00'),
            trade_count=10,
            first_trade_id=100,
            last_trade_id=110,
        )
        
        d = agg.to_dict()
        
        assert d['time'] == time
        assert d['symbol'] == 'BTC/USDT'
        assert d['open'] == '50000.00'
        assert d['trade_count'] == 10


class TestMultiSymbolAggregator:
    """Test MultiSymbolAggregator."""
    
    @pytest.mark.asyncio
    async def test_add_trade(self) -> None:
        """Test adding trade."""
        candles = []
        
        async def on_candle(symbol: str, candle: TradeAggregation) -> None:
            candles.append((symbol, candle))
        
        aggregator = MultiSymbolAggregator(on_candle=on_candle)
        
        trade = AggTrade(
            event_type='aggTrade',
            event_time=123456789,
            symbol='BTCUSDT',
            agg_trade_id=12345,
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            first_trade_id=100,
            last_trade_id=105,
            trade_time=123456789,
            is_buyer_maker=False,
        )
        
        await aggregator.add_trade('BTC/USDT', trade)
        
        # No candle emitted yet (same window)
        assert len(candles) == 0
        
        stats = aggregator.get_stats()
        assert stats['symbols'] == 1


class TestDatabaseWriter:
    """Test DatabaseWriter."""
    
    @pytest.mark.asyncio
    async def test_write_candle(self) -> None:
        """Test writing candle."""
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_conn.executemany = AsyncMock()
        
        writer = DatabaseWriter(
            db_pool=mock_pool,
            symbol_id=1,
        )
        
        time = datetime.now(timezone.utc)
        candle = TradeAggregation(
            time=time,
            symbol='BTC/USDT',
            open=Decimal('50000.00'),
            high=Decimal('51000.00'),
            low=Decimal('49000.00'),
            close=Decimal('50500.00'),
            volume=Decimal('1.0'),
            quote_volume=Decimal('50000.00'),
            trade_count=10,
            first_trade_id=100,
            last_trade_id=110,
        )
        
        await writer.write_candle(candle)
        
        # Candle should be in buffer (not flushed yet)
        stats = writer.get_stats()
        assert stats['buffer_size'] == 1
        assert stats['candles_written'] == 0
        
        # Flush
        await writer.flush()
        
        assert mock_conn.executemany.called
        stats = writer.get_stats()
        assert stats['candles_written'] == 1
        assert stats['buffer_size'] == 0
