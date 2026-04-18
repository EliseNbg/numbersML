"""
Backtesting system for Entry Point Model.

Walk Forward Validation is used because normal train/test split
is invalid for time series data.
"""

import numpy as np
import logging
from typing import List, Tuple, Dict

from ml.entry_model import EntryPointModel

logger = logging.getLogger(__name__)


def walk_forward_backtest(
    X: np.ndarray,
    y: np.ndarray,
    prices: np.ndarray,
    timestamps: np.ndarray,
    train_window: int = 86400,  # 1 day training window
    test_window: int = 3600,     # 1 hour test window
    threshold: float = 0.6
) -> Dict:
    """
    Perform Walk Forward Validation backtest.

    This is the ONLY valid way to test trading ML models.
    No data leakage, no look ahead bias.

    Args:
        X: Feature matrix
        y: Labels
        prices: Close prices array
        timestamps: Timestamp array
        train_window: Training samples per fold
        test_window: Test samples per fold

    Returns:
        Backtest results with equity curve and metrics
    """
    n = len(X)
    folds = []
    equity = 1.0
    equity_curve = []
    trades = []

    logger.info(f"Starting Walk Forward Backtest:")
    logger.info(f"  Total samples: {n}")
    logger.info(f"  Train window: {train_window/3600:.1f}h")
    logger.info(f"  Test window: {test_window/3600:.1f}h")
    logger.info(f"  Prediction threshold: {threshold:.2f}")

    position = 0
    entry_price = 0.0
    entry_time = None

    i = train_window

    while i < n - test_window:
        # Train on past data
        X_train = X[i - train_window : i]
        y_train = y[i - train_window : i]

        # Test on next window
        X_test = X[i : i + test_window]
        y_test = y[i : i + test_window]
        test_prices = prices[i : i + test_window]
        test_times = timestamps[i : i + test_window]

        model = EntryPointModel()
        model.train(X_train, y_train, X_test, y_test)

        # Predict
        probs, preds = model.predict(X_test, threshold=threshold)

        # Simulate trading
        fold_equity_start = equity
        fold_trades = 0

        for j in range(len(preds)):
            current_price = test_prices[j]
            current_time = test_times[j]

            if preds[j] == 1 and position == 0:
                # Enter long position
                position = 1
                entry_price = current_price
                entry_time = current_time
                logger.debug(f"ENTER long at {entry_price} time={entry_time}")

            elif position == 1:
                # Check exit conditions
                profit_pct = (current_price - entry_price) / entry_price

                if profit_pct >= 0.005 or profit_pct <= -0.002 or j == len(preds)-1:
                    # Exit position
                    position = 0
                    pnl = (current_price - entry_price) / entry_price - 0.001  # minus fees
                    equity *= (1 + pnl)

                    trades.append({
                        'entry_time': entry_time,
                        'exit_time': current_time,
                        'entry_price': entry_price,
                        'exit_price': current_price,
                        'pnl': pnl,
                        'duration': (current_time - entry_time).total_seconds()
                    })

                    fold_trades += 1
                    logger.debug(f"EXIT at {current_price} PnL: {pnl*100:.3f}%")

            equity_curve.append(equity)

        folds.append({
            'start_idx': i,
            'end_idx': i + test_window,
            'trades': fold_trades,
            'equity_start': fold_equity_start,
            'equity_end': equity,
            'return': (equity - fold_equity_start) / fold_equity_start
        })

        logger.info(f"Fold {len(folds)}: {fold_trades} trades, return: {folds[-1]['return']*100:.2f}%, equity: {equity:.4f}")

        # Move window forward
        i += test_window

    # Calculate metrics
    total_trades = len(trades)
    wins = sum(1 for t in trades if t['pnl'] > 0)
    losses = sum(1 for t in trades if t['pnl'] < 0)
    win_rate = wins / total_trades if total_trades > 0 else 0
    total_return = (equity - 1) * 100

    logger.info("=" * 60)
    logger.info("BACKTEST RESULTS:")
    logger.info(f"  Total trades:   {total_trades}")
    logger.info(f"  Win rate:       {win_rate*100:.1f}%")
    logger.info(f"  Total return:   {total_return:.2f}%")
    logger.info(f"  Final equity:   {equity:.4f}")
    logger.info(f"  Avg PnL:        {np.mean([t['pnl'] for t in trades])*100:.4f}%")
    logger.info(f"  Max drawdown:   {calculate_max_drawdown(equity_curve)*100:.2f}%")
    logger.info(f"  Profit factor:  {calculate_profit_factor(trades):.2f}")
    logger.info("=" * 60)

    return {
        'folds': folds,
        'trades': trades,
        'equity_curve': equity_curve,
        'metrics': {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'total_return': total_return,
            'final_equity': equity
        }
    }


def calculate_max_drawdown(equity_curve: List[float]) -> float:
    """Calculate maximum drawdown from equity curve."""
    peak = 1.0
    max_dd = 0.0

    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak
        if dd > max_dd:
            max_dd = dd

    return max_dd


def calculate_profit_factor(trades: List[dict]) -> float:
    """Calculate profit factor (gross profit / gross loss)."""
    gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))

    if gross_loss == 0:
        return float('inf')

    return gross_profit / gross_loss
