#!/usr/bin/env python3
"""
Feature Engineering Script: Add Technical Indicators to Wide Vectors.

This script enhances the input features in wide_vectors by adding technical indicators:
- ATR (Average True Range) - volatility measure
- EMA (Exponential Moving Average) - trend indicator (multiple periods)
- MACD (Moving Average Convergence Divergence) - momentum oscillator
- RSI (Relative Strength Index) - overbought/oversold
- SMA (Simple Moving Average) - trend indicator (multiple periods)
- Bollinger Bands - volatility bands

Usage:
    python3 add_technical_indicators.py

This will:
1. Load close prices from candles_1s
2. Calculate technical indicators
3. Update wide_vectors with enhanced features
4. Store indicator config for reproducibility
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import asyncpg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """Calculate technical indicators for ML features."""
    
    @staticmethod
    def calculate_sma(prices: np.ndarray, period: int) -> np.ndarray:
        """Simple Moving Average."""
        if len(prices) < period:
            return np.full(len(prices), np.nan)
        
        sma = np.convolve(prices, np.ones(period)/period, mode='valid')
        # Pad beginning with NaN
        result = np.concatenate([np.full(period - 1, np.nan), sma])
        return result
    
    @staticmethod
    def calculate_ema(prices: np.ndarray, period: int) -> np.ndarray:
        """Exponential Moving Average."""
        if len(prices) < period:
            return np.full(len(prices), np.nan)
        
        ema = np.zeros_like(prices)
        multiplier = 2.0 / (period + 1)
        
        # Start with SMA
        ema[period-1] = np.mean(prices[:period])
        
        # Calculate EMA
        for i in range(period, len(prices)):
            ema[i] = (prices[i] - ema[i-1]) * multiplier + ema[i-1]
        
        # Pad beginning with NaN
        ema[:period-1] = np.nan
        return ema
    
    @staticmethod
    def calculate_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
        """Relative Strength Index."""
        if len(prices) < period + 1:
            return np.full(len(prices), np.nan)
        
        # Calculate price changes
        deltas = np.diff(prices)
        
        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        # Calculate average gain and loss
        rsi = np.full(len(prices), np.nan)
        
        # First average
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        
        if avg_loss == 0:
            rsi[period] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[period] = 100.0 - (100.0 / (1.0 + rs))
        
        # Smoothed averages
        for i in range(period + 1, len(prices)):
            avg_gain = (avg_gain * (period - 1) + gains[i-1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i-1]) / period
            
            if avg_loss == 0:
                rsi[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi[i] = 100.0 - (100.0 / (1.0 + rs))
        
        return rsi
    
    @staticmethod
    def calculate_macd(
        prices: np.ndarray,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        MACD (Moving Average Convergence Divergence).
        
        Returns:
            macd_line: MACD line
            signal_line: Signal line
            histogram: MACD histogram
        """
        # Calculate EMAs
        ema_fast = TechnicalIndicators.calculate_ema(prices, fast_period)
        ema_slow = TechnicalIndicators.calculate_ema(prices, slow_period)
        
        # MACD line
        macd_line = ema_fast - ema_slow
        
        # Signal line (EMA of MACD)
        # Skip NaN values at beginning
        valid_macd = macd_line[~np.isnan(macd_line)]
        if len(valid_macd) < signal_period:
            signal_line = np.full(len(macd_line), np.nan)
        else:
            signal_valid = TechnicalIndicators.calculate_ema(valid_macd, signal_period)
            signal_line = np.full(len(macd_line), np.nan)
            signal_line[~np.isnan(macd_line)] = signal_valid
        
        # Histogram
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    @staticmethod
    def calculate_atr(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 14
    ) -> np.ndarray:
        """Average True Range."""
        if len(high) < period:
            return np.full(len(high), np.nan)
        
        # Calculate true range
        tr1 = high - low
        tr2 = np.abs(high[1:] - close[:-1])
        tr3 = np.abs(low[1:] - close[:-1])
        
        # Pad first element
        tr1 = np.concatenate([[np.nan], tr1[1:]])
        tr2 = np.concatenate([[np.nan], tr2])
        tr3 = np.concatenate([[np.nan], tr3])
        
        # True range
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        
        # ATR (simple moving average of TR)
        atr = TechnicalIndicators.calculate_sma(tr, period)
        
        return atr
    
    @staticmethod
    def calculate_bollinger_bands(
        prices: np.ndarray,
        period: int = 20,
        num_std: float = 2.0
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Bollinger Bands.
        
        Returns:
            upper: Upper band
            middle: Middle band (SMA)
            lower: Lower band
        """
        # Middle band (SMA)
        middle = TechnicalIndicators.calculate_sma(prices, period)
        
        # Rolling standard deviation
        upper = np.full(len(prices), np.nan)
        lower = np.full(len(prices), np.nan)
        
        for i in range(period - 1, len(prices)):
            window = prices[i-period+1:i+1]
            std = np.std(window)
            upper[i] = middle[i] + num_std * std
            lower[i] = middle[i] - num_std * std
        
        return upper, middle, lower


async def enhance_wide_vectors(
    db_pool: asyncpg.Pool,
    symbol_id: int,
    batch_size: int = 10000
) -> Dict:
    """
    Enhance wide vectors with technical indicators.
    
    Args:
        db_pool: Database connection pool
        symbol_id: Symbol ID to process
        batch_size: Number of rows to process at once
    
    Returns:
        Statistics dict
    """
    logger.info(f"Enhancing wide vectors for symbol {symbol_id}")
    
    async with db_pool.acquire() as conn:
        # Get total count
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM wide_vectors WHERE vector_size < 100"
        )
        logger.info(f"Found {total} wide vectors to enhance")
        
        if total == 0:
            logger.info("No vectors need enhancement")
            return {'processed': 0, 'errors': 0}
        
        # Get all wide vectors with close prices
        rows = await conn.fetch("""
            SELECT
                wv.id,
                wv.time,
                wv.vector,
                wv.vector_size,
                c.close,
                c.high,
                c.low,
                c.volume
            FROM wide_vectors wv
            LEFT JOIN candles_1s c ON c.time = wv.time AND c.symbol_id = $1
            WHERE wv.vector_size < 100
              AND c.close IS NOT NULL
            ORDER BY wv.time
        """, symbol_id)
        
        if not rows:
            logger.warning("No data found")
            return {'processed': 0, 'errors': 0}
        
        # Extract close prices
        close_prices = np.array([float(r['close']) for r in rows], dtype=np.float64)
        high_prices = np.array([float(r['high']) for r in rows], dtype=np.float64)
        low_prices = np.array([float(r['low']) for r in rows], dtype=np.float64)
        volumes = np.array([float(r['volume']) for r in rows], dtype=np.float64)
        
        logger.info(f"Loaded {len(close_prices)} price points")
        
        # Calculate technical indicators
        logger.info("Calculating technical indicators...")
        
        # SMA (multiple periods)
        sma_10 = TechnicalIndicators.calculate_sma(close_prices, 10)
        sma_20 = TechnicalIndicators.calculate_sma(close_prices, 20)
        sma_50 = TechnicalIndicators.calculate_sma(close_prices, 50)
        
        # EMA (multiple periods)
        ema_10 = TechnicalIndicators.calculate_ema(close_prices, 10)
        ema_20 = TechnicalIndicators.calculate_ema(close_prices, 20)
        ema_50 = TechnicalIndicators.calculate_ema(close_prices, 50)
        
        # RSI
        rsi_14 = TechnicalIndicators.calculate_rsi(close_prices, 14)
        
        # MACD
        macd_line, signal_line, macd_hist = TechnicalIndicators.calculate_macd(close_prices)
        
        # ATR
        atr_14 = TechnicalIndicators.calculate_atr(high_prices, low_prices, close_prices, 14)
        
        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = TechnicalIndicators.calculate_bollinger_bands(close_prices, 20)
        
        # Handle NaN values (replace with 0 for ML features)
        indicators = np.column_stack([
            np.nan_to_num(sma_10, nan=0.0),
            np.nan_to_num(sma_20, nan=0.0),
            np.nan_to_num(sma_50, nan=0.0),
            np.nan_to_num(ema_10, nan=0.0),
            np.nan_to_num(ema_20, nan=0.0),
            np.nan_to_num(ema_50, nan=0.0),
            np.nan_to_num(rsi_14, nan=50.0),  # RSI midpoint
            np.nan_to_num(macd_line, nan=0.0),
            np.nan_to_num(signal_line, nan=0.0),
            np.nan_to_num(macd_hist, nan=0.0),
            np.nan_to_num(atr_14, nan=0.0),
            np.nan_to_num(bb_upper, nan=0.0),
            np.nan_to_num(bb_middle, nan=0.0),
            np.nan_to_num(bb_lower, nan=0.0),
            np.log1p(volumes),  # Log volume
        ])
        
        logger.info(f"Calculated {indicators.shape[1]} technical indicators")
        
        # Update wide vectors
        logger.info("Updating wide vectors in database...")
        
        processed = 0
        errors = 0
        
        async with conn.transaction():
            for i, row in enumerate(rows):
                try:
                    # Parse existing vector
                    existing_vector = np.array(json.loads(row['vector']), dtype=np.float32)
                    
                    # Append indicators
                    enhanced_vector = np.concatenate([
                        existing_vector,
                        indicators[i].astype(np.float32)
                    ])
                    
                    # Update in database
                    await conn.execute("""
                        UPDATE wide_vectors
                        SET vector = $1,
                            vector_size = $2
                        WHERE id = $3
                    """, json.dumps(enhanced_vector.tolist()), len(enhanced_vector), row['id'])
                    
                    processed += 1
                    
                    if processed % 1000 == 0:
                        logger.info(f"Processed {processed}/{len(rows)} vectors")
                        
                except Exception as e:
                    errors += 1
                    if errors % 100 == 0:
                        logger.error(f"Error processing vector {row['id']}: {e}")
        
        logger.info(f"Enhancement complete: {processed} processed, {errors} errors")
        
        # Save indicator config
        indicator_config = {
            'timestamp': datetime.now().isoformat(),
            'symbol_id': symbol_id,
            'indicators': [
                'SMA_10', 'SMA_20', 'SMA_50',
                'EMA_10', 'EMA_20', 'EMA_50',
                'RSI_14',
                'MACD_line', 'MACD_signal', 'MACD_histogram',
                'ATR_14',
                'BB_upper', 'BB_middle', 'BB_lower',
                'log_volume'
            ],
            'num_indicators': indicators.shape[1],
            'nan_handling': {
                'SMA/EMA': 'Replaced with 0',
                'RSI': 'Replaced with 50 (midpoint)',
                'MACD/ATR/BB': 'Replaced with 0',
                'Volume': 'Log transformed (log1p)'
            }
        }
        
        config_file = Path("ml/models/indicator_config.json")
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, 'w') as f:
            json.dump(indicator_config, f, indent=2)
        
        logger.info(f"Indicator config saved to: {config_file}")
        
        return {
            'processed': processed,
            'errors': errors,
            'num_indicators': indicators.shape[1],
            'total_features': len(json.loads(rows[0]['vector'])) + indicators.shape[1]
        }


async def main():
    """Main entry point."""
    import os
    
    # Database configuration
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '5432')),
        'database': os.getenv('DB_NAME', 'crypto_trading'),
        'user': os.getenv('DB_USER', 'crypto'),
        'password': os.getenv('DB_PASSWORD', 'crypto_secret'),
    }
    
    logger.info("Creating database connection pool...")
    db_pool = await asyncpg.create_pool(**db_config)
    
    try:
        # Get symbol ID for T01/USDC
        async with db_pool.acquire() as conn:
            symbol_id = await conn.fetchval(
                "SELECT id FROM symbols WHERE symbol = $1",
                "T01/USDC"
            )
            
            if not symbol_id:
                logger.error("Symbol T01/USDC not found")
                return
        
        # Enhance wide vectors
        stats = await enhance_wide_vectors(db_pool, symbol_id)
        
        logger.info(f"\n{'='*60}")
        logger.info("Feature Engineering Complete")
        logger.info(f"{'='*60}")
        logger.info(f"Vectors processed: {stats['processed']}")
        logger.info(f"Errors: {stats['errors']}")
        logger.info(f"Technical indicators added: {stats['num_indicators']}")
        logger.info(f"Total features per vector: {stats['total_features']}")
        logger.info(f"\nNext steps:")
        logger.info(f"  1. Retrain models with enhanced features")
        logger.info(f"  2. Update config.data.use_indicators = True")
        logger.info(f"  3. Train: python3 -m ml.train --model cnn_gru --symbol T01/USDC")
        
    finally:
        await db_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
