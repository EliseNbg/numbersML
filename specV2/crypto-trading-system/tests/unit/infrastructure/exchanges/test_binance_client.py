"""Tests for Binance WebSocket client."""

import pytest
from decimal import Decimal
from src.infrastructure.exchanges.binance_client import BinanceWebSocketClient


class TestBinanceWebSocketClient:
    """Test Binance WebSocket client."""
    
    def test_parse_symbol_usdt(self) -> None:
        """Test parsing USDT symbol."""
        client = BinanceWebSocketClient.__new__(BinanceWebSocketClient)
        
        result = client._parse_symbol('BTCUSDT')
        
        assert result == 'BTC/USDT'
    
    def test_parse_symbol_btc(self) -> None:
        """Test parsing BTC symbol."""
        client = BinanceWebSocketClient.__new__(BinanceWebSocketClient)
        
        result = client._parse_symbol('ETHBTC')
        
        assert result == 'ETH/BTC'
    
    def test_parse_symbol_eth(self) -> None:
        """Test parsing ETH symbol."""
        client = BinanceWebSocketClient.__new__(BinanceWebSocketClient)
        
        result = client._parse_symbol('USDCETH')
        
        assert result == 'USDC/ETH'
    
    def test_parse_symbol_unknown(self) -> None:
        """Test parsing unknown symbol format."""
        client = BinanceWebSocketClient.__new__(BinanceWebSocketClient)
        
        result = client._parse_symbol('UNKNOWN')
        
        assert result == 'UNKNOWN'
    
    def test_get_stats(self) -> None:
        """Test getting collection statistics."""
        client = BinanceWebSocketClient.__new__(BinanceWebSocketClient)
        client._stats = {'processed': 100, 'errors': 5}
        
        stats = client.get_stats()
        
        assert stats['processed'] == 100
        assert stats['errors'] == 5
