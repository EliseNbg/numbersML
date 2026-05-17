"""Unit tests for TradeSignal domain model."""
from decimal import Decimal
from uuid import UUID

import pytest

from src.domain.strategies.signal import SignalStatus, TradeSignal


class TestTradeSignal:
    """Tests for TradeSignal dataclass."""

    def test_default_values(self) -> None:
        signal = TradeSignal()
        assert isinstance(signal.signal_id, UUID)
        assert isinstance(signal.strategy_id, UUID)
        assert signal.strategy_name == ""
        assert signal.symbol == ""
        assert signal.side == "BUY"
        assert signal.order_type == "MARKET"
        assert signal.quantity == Decimal("0")
        assert signal.price is None
        assert signal.status == SignalStatus.PENDING

    def test_custom_values(self) -> None:
        signal = TradeSignal(
            strategy_name="TestStrategy",
            symbol="BTC/USDC",
            side="BUY",
            order_type="LIMIT",
            quantity=Decimal("0.001"),
            price=Decimal("67500.00"),
            metadata={"reason": "macd_cross"},
        )
        assert signal.strategy_name == "TestStrategy"
        assert signal.symbol == "BTC/USDC"
        assert signal.side == "BUY"
        assert signal.order_type == "LIMIT"
        assert signal.quantity == Decimal("0.001")
        assert signal.price == Decimal("67500.00")
        assert signal.metadata == {"reason": "macd_cross"}

    def test_to_dict(self) -> None:
        signal = TradeSignal(
            strategy_name="TestStrategy",
            symbol="BTC/USDC",
            side="BUY",
            quantity=Decimal("0.001"),
            price=Decimal("67500.00"),
        )
        d = signal.to_dict()
        assert d["strategy_name"] == "TestStrategy"
        assert d["symbol"] == "BTC/USDC"
        assert d["side"] == "BUY"
        assert d["quantity"] == 0.001
        assert d["price"] == 67500.00
        assert d["status"] == "PENDING"

    def test_to_dict_market_order_has_none_price(self) -> None:
        signal = TradeSignal(
            symbol="BTC/USDC",
            order_type="MARKET",
            price=None,
        )
        d = signal.to_dict()
        assert d["price"] is None

    def test_from_dict(self) -> None:
        data = {
            "signal_id": "12345678-1234-5678-1234-567812345678",
            "strategy_id": "87654321-4321-8765-4321-876543218765",
            "strategy_name": "TestStrategy",
            "symbol": "BTC/USDC",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.001,
            "price": 67500.00,
            "timestamp": "2026-05-17T10:30:00+00:00",
            "metadata": {"reason": "test"},
            "status": "EXECUTED",
        }
        signal = TradeSignal.from_dict(data)
        assert signal.strategy_name == "TestStrategy"
        assert signal.symbol == "BTC/USDC"
        assert signal.quantity == Decimal("0.001")
        assert signal.price == Decimal("67500")
        assert signal.status == SignalStatus.EXECUTED

    def test_roundtrip(self) -> None:
        original = TradeSignal(
            strategy_name="TestStrategy",
            symbol="BTC/USDC",
            side="SELL",
            order_type="LIMIT",
            quantity=Decimal("0.5"),
            price=Decimal("70000.00"),
            metadata={"take_profit": "71000"},
        )
        signal = TradeSignal.from_dict(original.to_dict())
        assert signal.strategy_name == original.strategy_name
        assert signal.symbol == original.symbol
        assert signal.side == original.side
        assert signal.quantity == original.quantity
        assert signal.price == original.price

    def test_frozen_dataclass(self) -> None:
        from dataclasses import FrozenInstanceError

        signal = TradeSignal(symbol="BTC/USDC")
        with pytest.raises(FrozenInstanceError):
            signal.symbol = "ETH/USDC"


class TestSignalStatus:
    """Tests for SignalStatus enum."""

    def test_all_statuses(self) -> None:
        assert SignalStatus.PENDING.value == "PENDING"
        assert SignalStatus.EXECUTED.value == "EXECUTED"
        assert SignalStatus.REJECTED.value == "REJECTED"
        assert SignalStatus.FAILED.value == "FAILED"
