"""
Unit tests for recovery manager and gap filling.

Tests:
- Gap detection
- Recovery loop behavior
- State persistence (UTC-aware datetimes)
- Trade processing
- Large gap handling
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.pipeline.recovery import BinanceRESTClient, RecoveryManager
from src.pipeline.websocket_manager import AggTrade


def make_trade(trade_id: int, symbol: str = "BTCUSDC", price: float = 67000.0) -> AggTrade:
    """Create a mock AggTrade."""
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return AggTrade(
        event_type="aggTrade",
        event_time=now_ms,
        symbol=symbol,
        agg_trade_id=trade_id,
        price=Decimal(str(price)),
        quantity=Decimal("0.001"),
        first_trade_id=trade_id,
        last_trade_id=trade_id,
        trade_time=now_ms,
        is_buyer_maker=True,
    )


def make_mock_pool():
    """Create a properly mocked asyncpg pool."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=1)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()

    @asynccontextmanager
    async def mock_acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = mock_acquire
    return pool, conn


class TestAggTrade:
    """Test AggTrade dataclass."""

    def test_timestamp_is_aware(self):
        trade = make_trade(1)
        ts = trade.timestamp
        assert ts.tzinfo is not None
        assert ts.tzinfo == timezone.utc

    def test_quote_quantity(self):
        trade = make_trade(1, price=67000.0)
        assert trade.quote_quantity == Decimal("67000.0") * Decimal("0.001")

    def test_to_dict(self):
        trade = make_trade(1)
        d = trade.to_dict()
        assert "timestamp" in d
        assert "quote_quantity" in d


class TestRecoveryManager:
    """Test RecoveryManager."""

    @pytest.fixture
    def mock_pool(self):
        pool, conn = make_mock_pool()
        return pool

    @pytest.fixture
    def on_trade_callback(self):
        return AsyncMock()

    @pytest.fixture
    def recovery(self, mock_pool, on_trade_callback):
        return RecoveryManager(
            symbol="BTC/USDC",
            db_pool=mock_pool,
            on_trade=on_trade_callback,
        )

    def test_init(self, recovery):
        assert recovery.symbol == "BTC/USDC"
        assert recovery._last_trade_id == 0
        assert not recovery._is_recovering

    @pytest.mark.asyncio
    async def test_process_trade_no_gap_first_trade(self, recovery, on_trade_callback):
        """First trade should not trigger gap detection."""
        trade = make_trade(100)
        result = await recovery.process_trade(trade)
        assert result is True
        assert recovery._last_trade_id == 100
        # on_trade is NOT called by process_trade (caller handles it)
        on_trade_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_trade_sequential_no_gap(self, recovery):
        """Sequential trades should not trigger gap detection."""
        await recovery.process_trade(make_trade(100))
        await recovery.process_trade(make_trade(101))
        await recovery.process_trade(make_trade(102))
        assert recovery._last_trade_id == 102

    @pytest.mark.asyncio
    async def test_process_trade_detects_gap(self, recovery):
        """Gap in trade IDs should trigger recovery."""
        await recovery.process_trade(make_trade(100))
        # Next trade jumps to 105 - gap of 4 trades
        with patch.object(recovery, '_recover_gap', new_callable=AsyncMock) as mock_recover:
            await recovery.process_trade(make_trade(105))
            # Give time for the task to be created
            await asyncio.sleep(0.1)
            assert recovery._stats['gaps_detected'] == 1

    @pytest.mark.asyncio
    async def test_process_trade_updates_timestamp(self, recovery):
        """Trade processing should update last_timestamp."""
        trade = make_trade(100)
        await recovery.process_trade(trade)
        assert recovery._last_timestamp == trade.timestamp
        assert recovery._last_timestamp.tzinfo == timezone.utc

    @pytest.mark.asyncio
    async def test_state_timestamp_aware(self, recovery):
        """Persisted timestamps should be timezone-aware."""
        trade = make_trade(100)
        await recovery.process_trade(trade)
        # The timestamp stored should be aware
        assert recovery._last_timestamp.tzinfo is not None


class TestRecoveryGapHandling:
    """Test gap recovery behavior."""

    @pytest.fixture
    def mock_rest_client(self):
        client = AsyncMock(spec=BinanceRESTClient)
        return client

    @pytest.fixture
    def mock_pool(self):
        pool, conn = make_mock_pool()
        return pool

    @pytest.mark.asyncio
    async def test_recovery_loop_calls_on_trade(self):
        """Recovery should call on_trade for each recovered trade."""
        pool, _ = make_mock_pool()
        recovered_trades = []
        async def on_trade(trade):
            recovered_trades.append(trade)

        recovery = RecoveryManager(
            symbol="BTC/USDC",
            db_pool=pool,
            on_trade=on_trade,
        )

        # Mock REST client to return trades
        mock_trades = [make_trade(i) for i in range(100, 105)]
        recovery._rest_client = AsyncMock()
        recovery._rest_client.get_agg_trades = AsyncMock(return_value=mock_trades)

        await recovery._recover_gap(from_id=100, to_id=104)

        assert len(recovered_trades) == 5
        assert recovery._stats['trades_recovered'] == 5

    @pytest.mark.asyncio
    async def test_recovery_respects_to_id(self):
        """Recovery should not process trades beyond to_id."""
        pool, _ = make_mock_pool()
        recovered_trades = []
        async def on_trade(trade):
            recovered_trades.append(trade)

        recovery = RecoveryManager(
            symbol="BTC/USDC",
            db_pool=pool,
            on_trade=on_trade,
        )

        # REST returns trades 100-110, but to_id is 104
        mock_trades = [make_trade(i) for i in range(100, 111)]
        recovery._rest_client = AsyncMock()
        recovery._rest_client.get_agg_trades = AsyncMock(return_value=mock_trades)

        await recovery._recover_gap(from_id=100, to_id=104)

        # Should only process trades 100-104
        assert len(recovered_trades) == 5

    @pytest.mark.asyncio
    async def test_recovery_loops_for_large_gaps(self):
        """Recovery should loop for gaps larger than 1000 trades."""
        pool, _ = make_mock_pool()
        recovered_trades = []
        async def on_trade(trade):
            recovered_trades.append(trade)

        recovery = RecoveryManager(
            symbol="BTC/USDC",
            db_pool=pool,
            on_trade=on_trade,
        )

        # First call returns 1000 trades, second returns 500
        batch1 = [make_trade(i) for i in range(100, 1100)]
        batch2 = [make_trade(i) for i in range(1100, 1550)]

        recovery._rest_client = AsyncMock()
        recovery._rest_client.get_agg_trades = AsyncMock(side_effect=[batch1, batch2, []])

        await recovery._recover_gap(from_id=100, to_id=1549)

        # Should have called REST API multiple times
        assert recovery._rest_client.get_agg_trades.call_count >= 2
        assert len(recovered_trades) == 1450

    @pytest.mark.asyncio
    async def test_recovery_calls_on_trade_for_each(self):
        """Recovery should call on_trade for each recovered trade."""
        pool, _ = make_mock_pool()
        recovered = []
        async def on_trade(trade):
            recovered.append(trade)

        recovery = RecoveryManager(
            symbol="BTC/USDC",
            db_pool=pool,
            on_trade=on_trade,
        )

        mock_trades = [make_trade(i) for i in range(100, 105)]
        recovery._rest_client = AsyncMock()
        recovery._rest_client.get_agg_trades = AsyncMock(return_value=mock_trades)

        await recovery._recover_gap(from_id=100, to_id=104)

        # Each recovered trade should be passed to on_trade
        assert len(recovered) == 5
        assert recovery._last_trade_id == 104


class TestRecoveryInitialization:
    """Test recovery manager initialization from DB."""

    @pytest.mark.asyncio
    async def test_initialize_loads_state(self):
        """Initialize should load state from database."""
        pool, conn = make_mock_pool()
        conn.fetchval = AsyncMock(return_value=1)
        conn.fetchrow = AsyncMock(return_value={
            'last_trade_id': 12345,
            'last_timestamp': datetime(2026, 4, 1, 5, 0, 0),
            'is_recovering': False,
            'gaps_detected': 5,
            'trades_processed': 1000,
        })

        recovery = RecoveryManager(
            symbol="BTC/USDC",
            db_pool=pool,
            on_trade=AsyncMock(),
        )
        await recovery.initialize()

        assert recovery._last_trade_id == 12345
        assert recovery._stats['gaps_detected'] == 5

    @pytest.mark.asyncio
    async def test_initialize_handles_missing_state(self):
        """Initialize should handle missing pipeline_state gracefully."""
        pool, conn = make_mock_pool()
        conn.fetchval = AsyncMock(return_value=1)
        conn.fetchrow = AsyncMock(return_value=None)

        recovery = RecoveryManager(
            symbol="BTC/USDC",
            db_pool=pool,
            on_trade=AsyncMock(),
        )
        await recovery.initialize()

        assert recovery._last_trade_id == 0


class TestBinanceRESTClient:
    """Test REST client trade parsing."""

    def test_trade_timestamp_aware(self):
        """Trades from REST should have aware timestamps."""
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        trade = AggTrade(
            event_type="aggTrade",
            event_time=now_ms,
            symbol="BTCUSDC",
            agg_trade_id=1,
            price=Decimal("67000"),
            quantity=Decimal("0.001"),
            first_trade_id=1,
            last_trade_id=1,
            trade_time=now_ms,
            is_buyer_maker=True,
        )
        assert trade.timestamp.tzinfo == timezone.utc


class TestGapFillingEndToEnd:
    """Integration-style tests for gap filling (mocked DB)."""

    @pytest.mark.asyncio
    async def test_full_gap_detection_and_recovery(self):
        """Simulate: trade 100 arrives, then trade 110 (gap of 9)."""
        processed_trades = []
        async def on_trade(trade):
            processed_trades.append(trade)

        pool, conn = make_mock_pool()

        recovery = RecoveryManager(
            symbol="BTC/USDC",
            db_pool=pool,
            on_trade=on_trade,
        )

        # Mock REST to return trades 101-109
        mock_trades = [make_trade(i) for i in range(101, 110)]
        recovery._rest_client = AsyncMock()
        recovery._rest_client.get_agg_trades = AsyncMock(return_value=mock_trades)

        # Process trade 100 (no gap, state updated)
        await recovery.process_trade(make_trade(100))
        assert len(processed_trades) == 0  # on_trade NOT called by process_trade

        # Process trade 110 (gap detected, recovery fills 101-109 via on_trade)
        await recovery.process_trade(make_trade(110))

        # Recovery called on_trade for 101-109 (9 trades)
        # Trade 110 is NOT passed to on_trade by process_trade
        assert len(processed_trades) == 9
        assert recovery._last_trade_id == 110

    @pytest.mark.asyncio
    async def test_no_gap_for_consecutive_trades(self):
        """Consecutive trades should not trigger recovery."""
        pool, conn = make_mock_pool()

        recovery = RecoveryManager(
            symbol="BTC/USDC",
            db_pool=pool,
            on_trade=AsyncMock(),
        )

        for i in range(100, 200):
            await recovery.process_trade(make_trade(i))

        assert recovery._last_trade_id == 199
        assert recovery._stats['gaps_detected'] == 0


class TestPipelineRestartRecovery:
    """
    Test the scenario: pipeline ran before, stopped, then restarts.
    The recovery manager loads last_trade_id from DB and fills the gap.
    """

    @pytest.mark.asyncio
    async def test_restart_recovers_gap_from_previous_run(self):
        """
        Simulates: pipeline ran earlier with trades up to ID 1000.
        Pipeline stops. Hours later, restarts.
        First WebSocket trade is ID 1050 -> gap of 49 trades to recover.
        """
        recovered_trades = []
        async def on_trade(trade):
            recovered_trades.append(trade)

        pool, conn = make_mock_pool()
        # Simulate DB has state from previous run
        from datetime import datetime, timezone
        conn.fetchrow = AsyncMock(return_value={
            'last_trade_id': 1000,
            'last_timestamp': datetime(2026, 4, 1, 4, 0, 0, tzinfo=timezone.utc),
            'is_recovering': False,
            'gaps_detected': 0,
            'trades_processed': 1000,
        })

        recovery = RecoveryManager(
            symbol="BTC/USDC",
            db_pool=pool,
            on_trade=on_trade,
        )

        # Initialize loads state from DB
        await recovery.initialize()
        assert recovery._last_trade_id == 1000

        # Mock REST to return trades 1001-1049
        mock_trades = [make_trade(i) for i in range(1001, 1050)]
        recovery._rest_client = AsyncMock()
        recovery._rest_client.get_agg_trades = AsyncMock(return_value=mock_trades)

        # First trade after restart: ID 1050 (gap of 49)
        await recovery.process_trade(make_trade(1050))
        await asyncio.sleep(0.5)

        # Recovery called on_trade for 1001-1049 (49 trades)
        assert len(recovered_trades) == 49
        assert recovery._last_trade_id == 1050
        assert recovery._stats['gaps_detected'] == 1

    @pytest.mark.asyncio
    async def test_restart_with_no_gap(self):
        """
        Pipeline restarts but WebSocket sends the very next trade.
        No gap should be detected.
        """
        pool, conn = make_mock_pool()
        from datetime import datetime, timezone
        conn.fetchrow = AsyncMock(return_value={
            'last_trade_id': 5000,
            'last_timestamp': datetime(2026, 4, 1, 6, 0, 0, tzinfo=timezone.utc),
            'is_recovering': False,
            'gaps_detected': 0,
            'trades_processed': 5000,
        })

        recovery = RecoveryManager(
            symbol="ETH/USDC",
            db_pool=pool,
            on_trade=AsyncMock(),
        )

        await recovery.initialize()
        assert recovery._last_trade_id == 5000

        # Next trade is sequential
        await recovery.process_trade(make_trade(5001))
        await recovery.process_trade(make_trade(5002))

        assert recovery._last_trade_id == 5002
        assert recovery._stats['gaps_detected'] == 0

    @pytest.mark.asyncio
    async def test_restart_large_gap_loops_recovery(self):
        """
        Pipeline restarts after long downtime.
        Gap is 5000 trades (needs multiple REST batches).
        """
        recovered_trades = []
        async def on_trade(trade):
            recovered_trades.append(trade)

        pool, conn = make_mock_pool()
        from datetime import datetime, timezone
        conn.fetchrow = AsyncMock(return_value={
            'last_trade_id': 100000,
            'last_timestamp': datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc),
            'is_recovering': False,
            'gaps_detected': 2,
            'trades_processed': 100000,
        })

        recovery = RecoveryManager(
            symbol="BTC/USDC",
            db_pool=pool,
            on_trade=on_trade,
        )

        await recovery.initialize()
        assert recovery._last_trade_id == 100000

        # Mock REST: first batch 1001 trades, second batch 1000, third batch 999
        batch1 = [make_trade(i) for i in range(100001, 101001)]  # 1000 trades
        batch2 = [make_trade(i) for i in range(101001, 102001)]  # 1000 trades
        batch3 = [make_trade(i) for i in range(102001, 103001)]  # 1000 trades
        batch4 = [make_trade(i) for i in range(103001, 104001)]  # 1000 trades
        batch5 = [make_trade(i) for i in range(104001, 105000)]  # 999 trades

        recovery._rest_client = AsyncMock()
        recovery._rest_client.get_agg_trades = AsyncMock(
            side_effect=[batch1, batch2, batch3, batch4, batch5, []]
        )

        # First trade after restart at ID 105000
        await recovery.process_trade(make_trade(105000))
        await asyncio.sleep(1.0)

        # All 4999 recovered trades passed to on_trade
        assert len(recovered_trades) == 4999
        assert recovery._last_trade_id == 105000
        assert recovery._rest_client.get_agg_trades.call_count >= 5


class TestInitialRecovery:
    """
    Test the initial recovery flow that runs BEFORE WebSocket connects.
    This fills the gap from the last pipeline run to the current trade ID,
    preventing the race condition of constant small gap recoveries.
    """

    @pytest.mark.asyncio
    async def test_initial_recovery_fetches_missing_trades(self):
        """
        Pipeline had last_trade_id=1000.
        On startup, recover trades 1001-1500 BEFORE WebSocket connects.
        Then WebSocket delivers 1501 with no gap.
        """
        recovered_trades = []
        async def on_trade(trade):
            recovered_trades.append(trade)

        pool, conn = make_mock_pool()
        from datetime import datetime, timezone
        conn.fetchrow = AsyncMock(return_value={
            'last_trade_id': 1000,
            'last_timestamp': datetime(2026, 4, 1, 4, 0, 0, tzinfo=timezone.utc),
            'is_recovering': False,
            'gaps_detected': 0,
            'trades_processed': 1000,
        })

        recovery = RecoveryManager(
            symbol="BTC/USDC",
            db_pool=pool,
            on_trade=on_trade,
        )
        await recovery.initialize()
        assert recovery._last_trade_id == 1000

        # Simulate REST API returning trades 1001-1500
        mock_trades = [make_trade(i) for i in range(1001, 1501)]
        recovery._rest_client = AsyncMock()
        recovery._rest_client.get_agg_trades = AsyncMock(return_value=mock_trades)

        # Run recovery (as _initial_recovery would)
        await recovery._recover_gap(from_id=1001, to_id=1500)

        # All 500 trades were passed to on_trade by recovery
        assert len(recovered_trades) == 500
        assert recovery._last_trade_id == 1500

        # Now WebSocket delivers 1501 - no gap, state updated
        await recovery.process_trade(make_trade(1501))
        assert recovery._last_trade_id == 1501
        assert len(recovered_trades) == 500  # on_trade NOT called by process_trade

    @pytest.mark.asyncio
    async def test_no_gap_after_initial_recovery(self):
        """
        After initial recovery, WebSocket should not trigger any gap recovery.
        """
        pool, conn = make_mock_pool()
        from datetime import datetime, timezone
        conn.fetchrow = AsyncMock(return_value={
            'last_trade_id': 5000,
            'last_timestamp': datetime(2026, 4, 1, 6, 30, 0, tzinfo=timezone.utc),
            'is_recovering': False,
            'gaps_detected': 0,
            'trades_processed': 5000,
        })

        recovery = RecoveryManager(
            symbol="ETH/USDC",
            db_pool=pool,
            on_trade=AsyncMock(),
        )
        await recovery.initialize()

        # WebSocket delivers next sequential trades
        for i in range(5001, 5100):
            await recovery.process_trade(make_trade(i))

        assert recovery._last_trade_id == 5099
        assert recovery._stats['gaps_detected'] == 0
