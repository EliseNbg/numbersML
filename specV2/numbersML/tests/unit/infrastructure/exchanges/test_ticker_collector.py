"""Tests for ticker collector service."""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from src.infrastructure.exchanges.ticker_collector import TickerCollector


class TestTickerCollector:
    """Test TickerCollector service."""
    
    def test_parse_symbol_usdt(self) -> None:
        """Test parsing USDT symbol."""
        collector = TickerCollector.__new__(TickerCollector)
        
        result = collector._parse_symbol('BTCUSDT')
        
        assert result == 'BTC/USDT'
    
    def test_parse_symbol_btc(self) -> None:
        """Test parsing BTC symbol."""
        collector = TickerCollector.__new__(TickerCollector)
        
        result = collector._parse_symbol('ETHBTC')
        
        assert result == 'ETH/BTC'
    
    def test_parse_symbol_eth(self) -> None:
        """Test parsing ETH symbol."""
        collector = TickerCollector.__new__(TickerCollector)
        
        result = collector._parse_symbol('USDCETH')
        
        assert result == 'USDC/ETH'
    
    def test_parse_symbol_unknown(self) -> None:
        """Test parsing unknown symbol format."""
        collector = TickerCollector.__new__(TickerCollector)
        
        result = collector._parse_symbol('UNKNOWN')
        
        assert result == 'UNKNOWN'
    
    def test_get_stats(self) -> None:
        """Test getting collection statistics."""
        collector = TickerCollector.__new__(TickerCollector)
        collector._stats = {'processed': 100, 'anomalies': 5, 'gaps': 2}
        
        stats = collector.get_stats()
        
        assert stats['processed'] == 100
        assert stats['anomalies'] == 5
        assert stats['gaps'] == 2
