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
                logger.info(f"ENTER long at {entry_price} time={entry_time}")

            elif position == 1:
                # Check exit conditions
                profit_pct = (current_price - entry_price) / entry_price
                profit_target = model.profit_target if model.profit_target is not None else 0.005
                stop_loss = model.stop_loss if model.stop_loss is not None else 0.002

                if profit_pct >= profit_target or profit_pct <= -stop_loss or j == len(preds)-1:
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
                    logger.info(f"EXIT at {current_price} PnL: {pnl*100:.3f}%")

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


if __name__ == '__main__':
    import argparse
    from datetime import datetime, timedelta, timezone
    from ml.entry_dataset import EntryPointDataset
    from ml.config import DatabaseConfig, DataConfig

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    parser = argparse.ArgumentParser(description='Backtest Entry Point Model')
    parser.add_argument('--model', required=True)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--hours', type=int, default=24)
    parser.add_argument('--threshold', type=float, default=0.11)
    parser.add_argument('--print-trades', action='store_true', help='Print individual trades')
    args = parser.parse_args()

    logger.info("✅ BACKTEST START | %s | %dh | th=%.4f", args.symbol, args.hours, args.threshold)
    
    # Load model
    import os
    model_path = args.model
    if not os.path.exists(model_path):
        model_path = os.path.join('ml', 'models', 'entry_point', args.model)
    model = EntryPointModel.load(model_path)
    
    # Load dataset for EXACT requested symbol
    db_config = DatabaseConfig()
    data_config = DataConfig()
    data_config.target_symbol = args.symbol
    
    ds = EntryPointDataset(
        db_config=db_config,
        data_config=data_config,
        start_time=datetime.now(timezone.utc)-timedelta(hours=args.hours),
        end_time=datetime.now(timezone.utc),
        profit_target=model.profit_target if model.profit_target is not None else 0.005,
        stop_loss=model.stop_loss if model.stop_loss is not None else 0.002,
        look_ahead=3900,
        balance_classes=False
    )

    # Run EXACT same backtest logic as Web API
    probabilities, _ = model.predict(np.vstack(ds.vectors), threshold=args.threshold)
    # ✅ Load REAL closing prices from dataset public attribute
    closes = np.array(ds.closes)
    timestamps = np.array([int(t.timestamp()) for t in ds.timestamps])

    # ✅ Exakt gleiche Trading Simulation wie Web API /api/backtest_ml/entry
    trades = []
    position = 0
    entry_price = 0.0
    entry_time = 0
    entry_counter = 0
    exit_counter = 0

    profit_target = 0.006
    stop_loss = 0.003

    logger.info(f"🔄 Starting trading simulation with threshold={args.threshold:.4f}")
    logger.info(f"   Profit Target: +{profit_target*100:.2f}% | Stop Loss: -{stop_loss*100:.2f}%")

    data_length = min(len(closes), len(timestamps), len(probabilities))
    for i in range(data_length):
        current_price = closes[i]
        current_time = timestamps[i]
        prob = probabilities[i]

        # ENTER LONG POSITION
        if prob >= args.threshold and position == 0:
            position = 1
            entry_price = current_price
            entry_time = current_time
            entry_counter += 1
            logger.info(f"✅ ENTER #{entry_counter} at price={entry_price:.6f} time={datetime.fromtimestamp(current_time)} prob={prob:.6f}")

        # ✅ EXIT POSITION LOGIC - CHECK IN EVERY SINGLE STEP!
        elif position == 1:
            profit_pct = (current_price - entry_price) / entry_price

            # ✅ DEBUG LOG EVERY SINGLE CANDLE WHILE POSITION IS OPEN
            logger.debug(f"   📊 POSITION OPEN: candle={i:6d} price={current_price:.6f} pnl={profit_pct*100:+.4f}%")

            # ✅ Check exit conditions ON EVERY SINGLE CANDLE!
            should_exit = (
                profit_pct >= profit_target 
                or profit_pct <= -stop_loss 
                or i == len(closes)-1
            )

            if should_exit:
                position = 0
                pnl = profit_pct - 0.002  # minus 0.2% fees

                trades.append({
                    'entry_time': int(entry_time),
                    'exit_time': int(current_time),
                    'entry_price': float(entry_price),
                    'exit_price': float(current_price),
                    'pnl': float(pnl),
                    'duration': int(current_time - entry_time)
                })

                exit_counter += 1
                logger.info(f"❌ EXIT  #{exit_counter} pnl={pnl*100:.4f}% price={current_price:.6f} duration={int(current_time - entry_time)}s")

    logger.info(f"✅ Trading simulation complete: entered={entry_counter} exited={exit_counter} total_trades={len(trades)}")

    # Calculate metrics
    win_rate = 0.0
    total_return = 0.0
    profit_factor = 0.0
    
    if trades:
        wins = sum(1 for t in trades if t['pnl'] > 0)
        win_rate = wins / len(trades)
        total_return = sum(t['pnl'] for t in trades)
        
        gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    logger.info("\n✅ FINALES ERGEBNIS:")
    logger.info("=" * 70)
    logger.info(f"✅ Gesamte Trades:      {len(trades)}")
    logger.info(f"✅ Trades pro Stunde:  {(len(trades)/args.hours):.2f}")
    logger.info(f"✅ Trades pro Tag:     {(len(trades)/args.hours * 24):.1f}")
    logger.info("")
    logger.info(f"📈 Win Rate:           {(win_rate * 100):.1f} %")
    logger.info(f"📈 Gesamt Gewinn:      {(total_return * 100):.2f} %")
    logger.info(f"📈 Profit Factor:      {profit_factor:.2f}")
    logger.info("=" * 70)
    
    if args.print_trades and len(trades) > 0:
        logger.info("\n📋 ABGESCHLOSSENE TRADES:")
        logger.info("-" * 70)
        
        for idx, trade in enumerate(trades):
            side = "✅" if trade['pnl'] > 0 else "❌"
