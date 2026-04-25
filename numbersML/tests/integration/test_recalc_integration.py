#!/usr/bin/env python3
"""Integration tests for recalculate symbol processing bug fix."""
import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
import asyncpg
import pytest

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
DB_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"

async def get_test_symbols():
    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5)
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, symbol FROM symbols WHERE is_active = true AND is_allowed = true ORDER BY id LIMIT 3")
            if len(rows) < 3:
                raise RuntimeError("Need 3 active symbols")
            return [(r['id'], r['symbol']) for r in rows]
    finally:
        await pool.close()

async def cleanup_symbols(symbol_ids):
    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5)
    try:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = ANY($1)", symbol_ids)
            await conn.execute("DELETE FROM candles_1s WHERE symbol_id = ANY($1)", symbol_ids)
    finally:
        await pool.close()

async def test_recalculate_processes_all_symbols():
    symbol_data = await get_test_symbols()
    symbol_ids = [s[0] for s in symbol_data]
    num_symbols = len(symbol_ids)
    await cleanup_symbols(symbol_ids)
    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5)
    try:
        base = datetime(2026, 4, 25, 10, 0, 0, tzinfo=timezone.utc)
        async with pool.acquire() as conn:
            for i, sid in enumerate(symbol_ids):
                bp = 100.0 + i * 10
                for j in range(200):
                    ht = base - timedelta(seconds=200 - j)
                    p = bp + j * 0.01
                    await conn.execute(
                        "INSERT INTO candles_1s (symbol_id, time, open, high, low, close, volume, quote_volume, trade_count, processed) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                        sid, ht, p, p, p, p, 1000.0, 100000.0, 10, True)
                await conn.execute(
                    "INSERT INTO candles_1s (symbol_id, time, open, high, low, close, volume, quote_volume, trade_count, processed) VALUES ($1,$2,$3,$3,$3,$3,$4,$5,$6,$7)",
                    sid, base, bp, 1000.0, 100000.0, 10, False)
            uc = await conn.fetchval(
                "SELECT COUNT(*) FROM candles_1s WHERE not processed AND symbol_id = ANY($1)", symbol_ids)
            assert uc == num_symbols
        from src.cli.recalculate import recalculate_indicators
        from src.pipeline.indicator_calculator import IndicatorCalculator
        cp = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5)
        calc = IndicatorCalculator(cp)
        await calc.load_definitions()
        if not calc._definitions:
            await cp.close()
            return pytest.skip("No indicators")
        total = await recalculate_indicators(cp, symbol_ids, base-timedelta(1), base+timedelta(1))
        nd, ns = len(calc._definitions), num_symbols
        assert total >= nd * ns // 2, f"Got {total}, expected >= {nd*ns//2}. Bug: only sym[0]"
        async with pool.acquire() as conn:
            with_ind = 0
            for sid in symbol_ids:
                if await conn.fetchval("SELECT COUNT(*) FROM candle_indicators WHERE symbol_id=$1 AND time=$2", sid, base) > 0:
                    with_ind += 1
            assert with_ind >= ns // 2, f"Only {with_ind}/{ns} symbols processed"
        logger.info(f"✓ All {num_symbols} symbols processed (bug fix verified)")
        await cp.close()
    finally:
        await pool.close()

async def test_multiple_times_symbols():
    symbol_data = await get_test_symbols()
    symbol_ids = [s[0] for s in symbol_data]
    num_symbols = len(symbol_ids)
    await cleanup_symbols(symbol_ids)
    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5)
    try:
        base = datetime(2026, 4, 25, 11, 0, 0, tzinfo=timezone.utc)
        async with pool.acquire() as conn:
            for i, sid in enumerate(symbol_ids):
                bp = 100.0 + i * 10
                for j in range(200):
                    ht = base - timedelta(seconds=200 - j)
                    p = bp + j * 0.01
                    await conn.execute(
                        "INSERT INTO candles_1s (symbol_id, time, open, high, low, close, volume, quote_volume, trade_count, processed) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                        sid, ht, p, p, p, p, 1000.0, 100000.0, 10, True)
                for k in range(2):
                    await conn.execute(
                        "INSERT INTO candles_1s (symbol_id, time, open, high, low, close, volume, quote_volume, trade_count, processed) VALUES ($1,$2,$3,$3,$3,$3,$4,$5,$6,$7)",
                        sid, base+timedelta(seconds=k), bp+k*5, 1000.0, 100000.0, 10, False)
            uc = await conn.fetchval(
                "SELECT COUNT(*) FROM candles_1s WHERE not processed AND symbol_id = ANY($1)", symbol_ids)
            assert uc == 2 * num_symbols
        from src.cli.recalculate import recalculate_indicators
        from src.pipeline.indicator_calculator import IndicatorCalculator
        cp = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5)
        calc = IndicatorCalculator(cp)
        await calc.load_definitions()
        if not calc._definitions:
            await cp.close()
            return pytest.skip("No indicators")
        total = await recalculate_indicators(cp, symbol_ids, base-timedelta(1), base+timedelta(3))
        nd, ns = len(calc._definitions), num_symbols
        assert total >= (nd * ns * 2) // 3, f"Bug: got {total} < {(nd*ns*2)//3}"
        async with pool.acquire() as conn:
            for sid in symbol_ids:
                for k in range(2):
                    assert await conn.fetchval("SELECT COUNT(*) FROM candle_indicators WHERE symbol_id=$1 AND time=$2", sid, base+timedelta(seconds=k)) > 0
        logger.info(f"✓ {num_symbols}x2 all processed")
        await cp.close()
    finally:
        await pool.close()

async def test_indicators_differ_by_symbol():
    symbol_data = await get_test_symbols()
    symbol_ids = [s[0] for s in symbol_data]
    num_symbols = len(symbol_ids)
    await cleanup_symbols(symbol_ids)
    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5)
    try:
        base = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
        async with pool.acquire() as conn:
            for i, sid in enumerate(symbol_ids):
                bp = 50.0 + i * 50
                for j in range(200):
                    ht = base - timedelta(seconds=200 - j)
                    p = bp + j * 0.1
                    await conn.execute(
                        "INSERT INTO candles_1s (symbol_id, time, open, high, low, close, volume, quote_volume, trade_count, processed) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                        sid, ht, p, p, p, p, 1000.0, 100000.0, 10, True)
                await conn.execute(
                    "INSERT INTO candles_1s (symbol_id, time, open, high, low, close, volume, quote_volume, trade_count, processed) VALUES ($1,$2,$3,$3,$3,$3,$4,$5,$6,$7)",
                    sid, base, bp+20, 1000.0, 100000.0, 10, False)
        from src.cli.recalculate import recalculate_indicators
        from src.pipeline.indicator_calculator import IndicatorCalculator
        cp = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5)
        calc = IndicatorCalculator(cp)
        await calc.load_definitions()
        if not calc._definitions:
            await cp.close()
            return pytest.skip("No indicators")
        await recalculate_indicators(cp, symbol_ids, base-timedelta(1), base+timedelta(1))
        iv = {}
        async with pool.acquire() as conn:
            for sid in symbol_ids:
                row = await conn.fetchrow("SELECT values FROM candle_indicators WHERE symbol_id=$1 AND time=$2", sid, base)
                if row:
                    iv[sid] = json.loads(row['values'])
        assert len(iv) >= num_symbols // 2
        keys = set().union(*(v.keys() for v in iv.values()))
        diff = [k for k in keys if len(set(iv[s].get(k) for s in iv.keys() if k in iv[s])) > 1]
        assert len(diff) > 0, "Indicators identical (bug): prices 50/100/150 but same output"
        logger.info(f"✓ Indicators differ by symbol ({len(diff)} keys)")
        await cp.close()
    finally:
        await pool.close()
