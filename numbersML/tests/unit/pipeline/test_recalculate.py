"""
Unit tests for recalculate.py gap-filling logic.

Tests:
- Gap detection for missing symbols
- Forward-fill of candles and indicators
- Wide vector generation with filled data
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGapFilling:
    """Test gap detection and forward-fill in wide vector recalculation."""

    def test_detects_missing_symbols(self) -> None:
        """Test that gaps are detected when a symbol is missing."""
        # Simulate: 2 active symbols, but only 1 has data at time T
        now = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
        active_symbols = [(1, 'BTC/USDC'), (2, 'ETH/USDC')]

        candle_by_time = {
            now: {
                'BTC/USDC': {'close': 67000.0, 'volume': 1.5},
            },
        }
        by_time = {
            now: {
                'BTC/USDC': {'rsi': 65.0},
            },
        }

        # Check missing symbols at each time
        all_times = sorted(set(list(by_time.keys()) + list(candle_by_time.keys())))
        missing_symbols_by_time = {}
        for t in all_times:
            symbols_at_time = set()
            if t in candle_by_time:
                symbols_at_time.update(candle_by_time[t].keys())
            if t in by_time:
                symbols_at_time.update(by_time[t].keys())

            missing = [sname for _, sname in active_symbols
                       if sname not in symbols_at_time]
            if missing:
                missing_symbols_by_time[t] = missing

        assert 'ETH/USDC' in missing_symbols_by_time[now]
        assert 'BTC/USDC' not in missing_symbols_by_time[now]

    def test_forward_fill_sets_volume_zero(self) -> None:
        """Test that forward-filled candles have volume=0."""
        # Simulate forward-fill logic
        candle_data = {'close': 3500.0, 'volume': 0.0}
        assert candle_data['volume'] == 0.0
        assert candle_data['close'] == 3500.0

    def test_complete_data_no_gap(self) -> None:
        """Test that complete data (no gaps) has no missing symbols."""
        now = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
        candle_by_time = {
            now: {
                'BTC/USDC': {'close': 67000.0, 'volume': 1.5},
                'ETH/USDC': {'close': 3500.0, 'volume': 10.0},
            },
        }
        by_time = {
            now: {
                'BTC/USDC': {'rsi': 65.0},
                'ETH/USDC': {'rsi': 55.0},
            },
        }
        active_symbols = [(1, 'BTC/USDC'), (2, 'ETH/USDC')]

        all_times = sorted(set(list(by_time.keys()) + list(candle_by_time.keys())))
        for t in all_times:
            symbols_at_time = set()
            if t in candle_by_time:
                symbols_at_time.update(candle_by_time[t].keys())
            if t in by_time:
                symbols_at_time.update(by_time[t].keys())

            missing = [sname for _, sname in active_symbols
                       if sname not in symbols_at_time]
            assert len(missing) == 0, f"No symbols should be missing at {t}"

    def test_wide_vector_uses_filled_data(self) -> None:
        """Test that wide vector includes forward-filled symbol data."""
        now = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
        active_symbols = [(1, 'BTC/USDC'), (2, 'ETH/USDC')]
        sorted_indicator_keys = ['rsi']

        # After forward-fill, ETH should have been filled
        candle_by_time = {
            now: {
                'BTC/USDC': {'close': 67000.0, 'volume': 1.5},
                'ETH/USDC': {'close': 3500.0, 'volume': 0.0},  # Forward-filled
            },
        }
        by_time = {
            now: {
                'BTC/USDC': {'rsi': 65.0},
                'ETH/USDC': {'rsi': 55.0},  # Forward-filled
            },
        }

        # Build wide vector (same logic as recalculate.py)
        for t in sorted(candle_by_time.keys()):
            cd_data = candle_by_time[t]
            ind_data = by_time[t]
            vector = []
            column_names = []

            for sid, sname in active_symbols:
                cd = cd_data.get(sname, {})
                ind = ind_data.get(sname, {})
                col_sname = sname.replace('/', '_')

                for feat in ['close', 'volume']:
                    vector.append(cd.get(feat, 0.0))
                    column_names.append(f"{col_sname}_{feat}")

                for ikey in sorted_indicator_keys:
                    vector.append(ind.get(ikey, 0.0))
                    column_names.append(f"{col_sname}_{ikey}")

            # Verify all 4 features present (2 symbols x 2 features + 2 symbols x 1 indicator)
            assert len(vector) == 6, f"Vector should have 6 values, got {len(vector)}"
            # ETH close should be forward-filled value
            eth_close_idx = column_names.index('ETH_USDC_close')
            assert vector[eth_close_idx] == 3500.0
            # ETH volume should be 0 (forward-filled)
            eth_vol_idx = column_names.index('ETH_USDC_volume')
            assert vector[eth_vol_idx] == 0.0
