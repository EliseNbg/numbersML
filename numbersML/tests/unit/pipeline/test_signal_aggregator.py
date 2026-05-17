"""Unit tests for SignalAggregator."""
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from src.domain.strategies.signal import SignalStatus, TradeSignal
from src.pipeline.signal_aggregator import SignalAggregator, SignalStats


class TestSignalStats:
    """Tests for SignalStats dataclass."""

    def test_default_values(self) -> None:
        stats = SignalStats()
        assert stats.total_signals == 0
        assert stats.buy_count == 0
        assert stats.sell_count == 0

    def test_to_dict(self) -> None:
        stats = SignalStats(
            total_signals=10,
            buy_count=6,
            sell_count=4,
            executed_count=8,
            rejected_count=1,
            failed_count=1,
            pending_count=0,
            avg_quantity=0.5,
        )
        result = stats.to_dict()
        assert result["total_signals"] == 10
        assert result["buy_count"] == 6
        assert result["avg_quantity"] == 0.5


class TestSignalAggregator:
    """Tests for SignalAggregator."""

    def _make_signal(
        self,
        strategy_id: str | None = None,
        symbol: str = "BTC/USDC",
        side: str = "BUY",
        status: SignalStatus = SignalStatus.PENDING,
        quantity: Decimal = Decimal("1.0"),
    ) -> TradeSignal:
        return TradeSignal(
            strategy_id=strategy_id or uuid4(),
            strategy_name="Test Strategy",
            symbol=symbol,
            side=side,
            order_type="MARKET",
            quantity=quantity,
            timestamp=datetime.now(UTC),
            status=status,
        )

    def test_add_and_retrieve_signal(self) -> None:
        aggregator = SignalAggregator()
        signal = self._make_signal()
        aggregator.add_signal(signal)
        recent = aggregator.get_recent(limit=10)
        assert len(recent) == 1
        assert recent[0].signal_id == signal.signal_id

    def test_get_recent_limit(self) -> None:
        aggregator = SignalAggregator()
        for _ in range(10):
            aggregator.add_signal(self._make_signal())
        recent = aggregator.get_recent(limit=3)
        assert len(recent) == 3

    def test_filter_by_strategy(self) -> None:
        aggregator = SignalAggregator()
        sid1 = uuid4()
        sid2 = uuid4()
        aggregator.add_signal(self._make_signal(strategy_id=sid1))
        aggregator.add_signal(self._make_signal(strategy_id=sid2))
        aggregator.add_signal(self._make_signal(strategy_id=sid1))

        filtered = aggregator.get_recent(strategy_id=sid1)
        assert len(filtered) == 2
        assert all(s.strategy_id == sid1 for s in filtered)

    def test_filter_by_symbol(self) -> None:
        aggregator = SignalAggregator()
        aggregator.add_signal(self._make_signal(symbol="BTC/USDC"))
        aggregator.add_signal(self._make_signal(symbol="ETH/USDC"))
        aggregator.add_signal(self._make_signal(symbol="BTC/USDC"))

        filtered = aggregator.get_recent(symbol="BTC/USDC")
        assert len(filtered) == 2
        assert all(s.symbol == "BTC/USDC" for s in filtered)

    def test_filter_by_strategy_and_symbol(self) -> None:
        aggregator = SignalAggregator()
        sid = uuid4()
        aggregator.add_signal(self._make_signal(strategy_id=sid, symbol="BTC/USDC"))
        aggregator.add_signal(self._make_signal(strategy_id=sid, symbol="ETH/USDC"))
        aggregator.add_signal(self._make_signal(strategy_id=uuid4(), symbol="BTC/USDC"))

        filtered = aggregator.get_recent(strategy_id=sid, symbol="BTC/USDC")
        assert len(filtered) == 1

    def test_get_stats(self) -> None:
        aggregator = SignalAggregator()
        sid = uuid4()
        aggregator.add_signal(self._make_signal(strategy_id=sid, side="BUY", status=SignalStatus.EXECUTED))
        aggregator.add_signal(self._make_signal(strategy_id=sid, side="SELL", status=SignalStatus.EXECUTED))
        aggregator.add_signal(self._make_signal(strategy_id=sid, side="BUY", status=SignalStatus.REJECTED))

        stats = aggregator.get_stats(sid)
        assert stats.total_signals == 3
        assert stats.buy_count == 2
        assert stats.sell_count == 1
        assert stats.executed_count == 2
        assert stats.rejected_count == 1

    def test_get_stats_empty(self) -> None:
        aggregator = SignalAggregator()
        stats = aggregator.get_stats(uuid4())
        assert stats.total_signals == 0

    def test_get_all_strategy_ids(self) -> None:
        aggregator = SignalAggregator()
        sid1 = uuid4()
        sid2 = uuid4()
        aggregator.add_signal(self._make_signal(strategy_id=sid1))
        aggregator.add_signal(self._make_signal(strategy_id=sid2))

        ids = aggregator.get_all_strategy_ids()
        assert set(ids) == {sid1, sid2}

    def test_clear_specific_strategy(self) -> None:
        aggregator = SignalAggregator()
        sid1 = uuid4()
        sid2 = uuid4()
        aggregator.add_signal(self._make_signal(strategy_id=sid1))
        aggregator.add_signal(self._make_signal(strategy_id=sid2))

        aggregator.clear(strategy_id=sid1)
        assert aggregator.get_signal_count(sid1) == 0
        assert aggregator.get_signal_count(sid2) == 1

    def test_clear_all(self) -> None:
        aggregator = SignalAggregator()
        sid = uuid4()
        aggregator.add_signal(self._make_signal(strategy_id=sid))
        aggregator.add_signal(self._make_signal(strategy_id=sid))

        aggregator.clear()
        assert aggregator.get_signal_count() == 0
        assert aggregator.get_all_strategy_ids() == []

    def test_get_signal_count(self) -> None:
        aggregator = SignalAggregator()
        sid = uuid4()
        aggregator.add_signal(self._make_signal(strategy_id=sid))
        aggregator.add_signal(self._make_signal(strategy_id=sid))

        assert aggregator.get_signal_count(sid) == 2
        assert aggregator.get_signal_count() == 2

    def test_get_signal_count_nonexistent(self) -> None:
        aggregator = SignalAggregator()
        assert aggregator.get_signal_count(uuid4()) == 0

    def test_to_dict_global(self) -> None:
        aggregator = SignalAggregator()
        sid = uuid4()
        aggregator.add_signal(self._make_signal(strategy_id=sid))

        result = aggregator.to_dict()
        assert result["total_strategies"] == 1
        assert result["total_signals"] == 1

    def test_to_dict_strategy(self) -> None:
        aggregator = SignalAggregator()
        sid = uuid4()
        aggregator.add_signal(self._make_signal(strategy_id=sid, side="BUY"))
        aggregator.add_signal(self._make_signal(strategy_id=sid, side="SELL"))

        result = aggregator.to_dict(strategy_id=sid)
        assert result["strategy_signals"] == 2
        assert "stats" in result
        assert result["stats"]["total_signals"] == 2

    def test_max_history_per_strategy(self) -> None:
        aggregator = SignalAggregator(max_history=5)
        sid = uuid4()
        for _ in range(10):
            aggregator.add_signal(self._make_signal(strategy_id=sid))

        assert aggregator.get_signal_count(sid) == 5

    def test_concurrent_add_signals(self) -> None:
        import threading

        aggregator = SignalAggregator()
        sid = uuid4()

        def add_signals(start: int) -> None:
            for i in range(start, start + 100):
                aggregator.add_signal(
                    self._make_signal(strategy_id=sid, quantity=Decimal(str(i)))
                )

        threads = [threading.Thread(target=add_signals, args=(i * 100,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert aggregator.get_signal_count(sid) == 500

    def test_stats_calculation_with_failed(self) -> None:
        aggregator = SignalAggregator()
        sid = uuid4()
        aggregator.add_signal(self._make_signal(strategy_id=sid, status=SignalStatus.FAILED))
        aggregator.add_signal(self._make_signal(strategy_id=sid, status=SignalStatus.PENDING))
        aggregator.add_signal(self._make_signal(strategy_id=sid, status=SignalStatus.EXECUTED))

        stats = aggregator.get_stats(sid)
        assert stats.failed_count == 1
        assert stats.pending_count == 1
        assert stats.executed_count == 1

    def test_avg_quantity_calculation(self) -> None:
        aggregator = SignalAggregator()
        sid = uuid4()
        aggregator.add_signal(self._make_signal(strategy_id=sid, quantity=Decimal("0.5")))
        aggregator.add_signal(self._make_signal(strategy_id=sid, quantity=Decimal("1.5")))

        stats = aggregator.get_stats(sid)
        assert stats.avg_quantity == pytest.approx(1.0, rel=1e-6)
