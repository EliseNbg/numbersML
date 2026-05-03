"""Tests for Symbol entity."""

from decimal import Decimal

import pytest

from src.domain.models.symbol import Symbol


class TestSymbolInitialization:
    """Test Symbol initialization and validation."""

    def test_create_valid_symbol(self) -> None:
        """Test creating a valid symbol."""
        symbol = Symbol(
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
            tick_size=Decimal("0.01"),
        )

        assert symbol.symbol == "BTC/USDT"
        assert symbol.base_asset == "BTC"
        assert symbol.is_active is False

    def test_symbol_must_have_valid_format(self) -> None:
        """Test that symbol format is validated."""
        with pytest.raises(ValueError, match="Invalid symbol format"):
            Symbol(symbol="INVALID")

    def test_tick_size_must_be_positive(self) -> None:
        """Test that tick_size must be positive."""
        with pytest.raises(ValueError, match="tick_size must be positive"):
            Symbol(
                symbol="BTC/USDT",
                tick_size=Decimal("-0.01"),
            )


class TestSymbolMethods:
    """Test Symbol methods."""

    @pytest.fixture
    def btc_symbol(self) -> Symbol:
        """Create BTC/USDT symbol for testing."""
        return Symbol(
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.00001"),
            min_notional=Decimal("10"),
        )

    def test_activate_symbol(self, btc_symbol: Symbol) -> None:
        """Test activating a symbol."""
        btc_symbol.activate()
        assert btc_symbol.is_active is True

    def test_deactivate_symbol(self, btc_symbol: Symbol) -> None:
        """Test deactivating a symbol."""
        btc_symbol.is_active = True
        btc_symbol.deactivate()
        assert btc_symbol.is_active is False

    def test_price_to_tick(self, btc_symbol: Symbol) -> None:
        """Test rounding price to tick size."""
        price = Decimal("50123.456")
        result = btc_symbol.price_to_tick(price)
        assert result == Decimal("50123.46")

    def test_is_valid_order_with_valid_order(self, btc_symbol: Symbol) -> None:
        """Test order validation with valid order."""
        price = Decimal("50000.00")
        quantity = Decimal("0.001")

        is_valid, error = btc_symbol.is_valid_order(price, quantity)

        assert is_valid is True
        assert error == ""

    def test_is_valid_order_below_min_notional(self, btc_symbol: Symbol) -> None:
        """Test order validation below minimum notional."""
        price = Decimal("50000.00")
        quantity = Decimal("0.00001")

        is_valid, error = btc_symbol.is_valid_order(price, quantity)

        assert is_valid is False
        assert "below minimum" in error
