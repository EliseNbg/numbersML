"""
PnL-optimized loss functions for trading models.

These losses are designed to align training with actual trading profit,
not generic ML metrics (MSE, BCE, accuracy).

Instead of predicting a label and optimizing classification metrics,
we optimize the actual expected trading performance:
  Sharpe ratio
  Expected PnL (with transaction costs)
  Risk-adjusted returns

All losses are differentiable and work with gradient-based training.
"""

import torch
import torch.nn.functional as F
from typing import Optional


def pnl_loss(
    pred_ret: torch.Tensor,
    true_ret: torch.Tensor,
    cost: float = 0.0005,
) -> torch.Tensor:
    """
    Differentiable PnL loss.

    Simulates a trading strategy where position size is a continuous
    function of predicted return, then penalizes negative PnL and
    adds transaction costs for turnover.

    Args:
        pred_ret: Predicted returns, shape (batch,). Can be any scale.
        true_ret: Realized returns (next-period), shape (batch,).
        cost: Per-unit transaction cost (e.g. 0.0005 = 5 bps).

    Returns:
        Negative mean PnL + cost penalty (scalar tensor to minimize).
    """
    # Soft position sizing — bounded, differentiable, monotonic
    # tanh ensures position ∈ [-1, 1] (100% long / short)
    position = torch.tanh(pred_ret * 5.0)

    # PnL per sample: position * realized return
    pnl = position * true_ret

    # Turnover penalty: discourage excessive trading
    # |position_t - position_{t-1}| encourages stable positions
    if position.shape[0] > 1:
        turnover = torch.abs(position[1:] - position[:-1]).mean()
    else:
        turnover = torch.tensor(0.0, device=position.device)

    return -pnl.mean() + cost * turnover


def sharpe_loss(
    pred_ret: torch.Tensor,
    true_ret: torch.Tensor,
) -> torch.Tensor:
    """
    Sharpe ratio maximization loss.

    Directly optimizes risk‑adjusted return: mean(pnl) / std(pnl).
    More robust than raw PnL because it penalizes volatility.

    Args:
        pred_ret: Predicted returns (any scale).
        true_ret: Realized returns.

    Returns:
        Negative Sharpe ratio (scalar to minimize).
    """
    position = torch.tanh(pred_ret * 5.0)
    pnl = position * true_ret

    mean_pnl = pnl.mean()
    std_pnl = pnl.std() + 1e-8  # avoid div by zero

    sharpe = mean_pnl / std_pnl
    return -sharpe


def risk_adjusted_loss(
    pred_ret: torch.Tensor,
    pred_risk: torch.Tensor,
    true_ret: torch.Tensor,
    risk_penalty: float = 0.1,
) -> torch.Tensor:
    """
    Loss that leverages a learned risk head.

    The model predicts both expected return (pred_ret) and predicted
    downside/risk (pred_risk). Position is sized as ret / risk (Kelly-like).
    Risk penalty encourages accurate volatility forecasting.

    Args:
        pred_ret:  Predicted return (batch,).
        pred_risk: Predicted risk / uncertainty (batch,), must be ≥0.
        true_ret:  Realized return (batch,).
        risk_penalty: Weight for underestimating risk term.

    Returns:
        Scalar loss to minimize.
    """
    # Position sizing: Kelly criterion-inspired
    # Larger predicted return → larger position
    # Larger predicted risk → smaller position
    position = torch.tanh(pred_ret / (pred_risk + 1e-6))

    pnl = position * true_ret

    # Risk penalty: if realized absolute return > predicted risk,
    # we underestimated risk → penalize
    risk_error = (torch.abs(true_ret) - pred_risk).clamp(min=0.0)
    risk_pen = risk_error.mean()

    return -pnl.mean() + risk_penalty * risk_pen


def expected_value_loss(
    pred_ret: torch.Tensor,
    true_ret: torch.Tensor,
    thresholds: torch.Tensor,
    profit: float,
    stop: float,
) -> torch.Tensor:
    """
    Loss based on expected value of a threshold‑based binary strategy.

    Args:
        pred_ret:  Model output (score) for each sample.
        true_ret:  Realized return.
        thresholds: Tensor of threshold values to sweep (learnable or fixed).
        profit:    Profit target (e.g. 0.0075).
        stop:      Stop loss (e.g. 0.0025).

    Returns:
        Negative expected value (to minimize).
    """
    # This is a placeholder; in practice you would:
    #  - binarize positions using pred_ret > threshold
    #  - compute per-sample PnL: +profit if long & hit, -stop if long & miss
    #  - smooth threshold selection via soft approximation
    raise NotImplementedError("expected_value_loss needs threshold tensor")


__all__ = [
    "pnl_loss",
    "sharpe_loss",
    "risk_adjusted_loss",
    "expected_value_loss",
]
