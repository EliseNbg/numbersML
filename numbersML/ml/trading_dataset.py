"""
Dataset for PnL‑optimized TradingTCN training.

Unlike WideVectorDataset which returns sigmoid‑scaled targets in [0,1],
this dataset provides raw (or standardized) next‑period returns so that
PnL‑aligned losses can operate directly on monetary outcomes.

Key features:
  - Targets are continuous returns: (price[t+H] - price[t]) / price[t]
  - Optional standardization (zero‑mean, unit‑var) using training set stats
  - Causal split: look‑ahead padding accounted for exactly
  - Optional stride to reduce sample overlap for 1‑second data
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import numpy as np
import psycopg2
import torch
from torch.utils.data import Dataset

from ml.config import DatabaseConfig, DataConfig

logger = logging.getLogger(__name__)


class TradingDataset(Dataset):
    """
    Dataset for training the TradingTCN model with raw/pnl‑aligned targets.

    Loads wide_vectors from PostgreSQL and pairs them with the
    *future* logarithmic or percentage return over ``prediction_horizon``.
    Targets are returned as float32 scalars (no sigmoid squashing).
    """

    def __init__(
        self,
        db_config: DatabaseConfig,
        data_config: DataConfig,
        start_time: datetime,
        end_time: datetime,
        mean: Optional[np.ndarray] = None,
        std: Optional[np.ndarray] = None,
        feature_mask: Optional[np.ndarray] = None,
        sequence_length: int = 120,
        normalize_returns: bool = False,
        clip_returns: float = 0.02,
        return_stride: int = 1,
    ):
        """
        Args:
            db_config: Database connection parameters.
            data_config: Data‑level config (target_symbol, prediction_horizon…).
            start_time / end_time: Chronological window (inclusive start, exclusive end).
            mean / std: Feature normalization statistics (fit on training set if None).
            feature_mask: Boolean mask of features to keep.
            sequence_length: Number of consecutive wide_vectors per sample.
            normalize_returns: If True, standardize return distribution (zero mean, unit var)
                                using statistics computed on this split.
            clip_returns: Maximum absolute return (for stability). 0.02 = ±2%.
            return_stride: Stride for down‑sampling consecutive samples to reduce
                           autocorrelation (1 = use every sample).
        """
        self.db_config = db_config
        self.data_config = data_config
        self.start_time = start_time
        self.end_time = end_time
        self.sequence_length = sequence_length
        self.normalize_returns = normalize_returns
        self.clip_returns = clip_returns
        self.return_stride = return_stride

        # Normalization cache (filled on first load if not provided)
        self.mean = mean
        self.std = std
        self.feature_mask = feature_mask

        # Load data from DB
        self.vectors, self.targets, self.timestamps, self.column_names = self._load_data()

        logger.info(
            f"TradingDataset loaded: {len(self.vectors)} vectors, "
            f"{len(self.targets)} targets, {len(self.timestamps)} timestamps, "
            f"{len(self.column_names)} feature columns"
        )

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def _load_data(self) -> Tuple[List[np.ndarray], List[float], List[datetime], List[str]]:
        """Fetch wide_vectors and compute raw next‑period returns."""
        conn = psycopg2.connect(
            host=self.db_config.host,
            port=self.db_config.port,
            dbname=self.db_config.dbname,
            user=self.db_config.user,
            password=self.db_config.password,
        )

        try:
            with conn.cursor() as cur:
                # Resolve symbol_id
                cur.execute(
                    "SELECT id FROM symbols WHERE symbol = %s",
                    (self.data_config.target_symbol,),
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError(f"Symbol '{self.data_config.target_symbol}' not found")
                symbol_id = row[0]

                # Load wide_vectors + close prices
                query = """
                    SELECT
                        wv.time,
                        wv.vector,
                        wv.vector_size,
                        wv.column_names,
                        c.close
                    FROM wide_vectors wv
                    JOIN candles_1s c ON c.time = wv.time AND c.symbol_id = %s
                    WHERE wv.time >= %s AND wv.time < %s
                      AND wv.vector_size >= 50
                      AND c.close IS NOT NULL
                    ORDER BY wv.time
                """
                cur.execute(query, (symbol_id, self.start_time, self.end_time))

                vectors_raw: List[np.ndarray] = []
                closes: List[float] = []
                timestamps: List[datetime] = []
                column_names: List[str] = []
                prev_size: Optional[int] = None

                while True:
                    batch = cur.fetchmany(5000)
                    if not batch:
                        break
                    for ts, vector_json, vec_size, cols_json, close in batch:
                        if isinstance(vector_json, str):
                            vec = np.array(json.loads(vector_json), dtype=np.float32)
                        else:
                            vec = np.array(vector_json, dtype=np.float32)

                        # DATA QUALITY: Handle NaN values from indicators
                        # Some technical indicators return NaN when they don't have enough history
                        if np.isnan(vec).any():
                            vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)

                        # Pad / truncate to fixed length
                        if prev_size is None:
                            prev_size = len(vec)
                        elif len(vec) != prev_size:
                            if len(vec) < prev_size:
                                vec = np.pad(vec, (0, prev_size - len(vec)))
                            else:
                                vec = vec[:prev_size]

                        vectors_raw.append(vec)
                        closes.append(float(close))
                        timestamps.append(ts)
                        if not column_names and cols_json is not None:
                            if isinstance(cols_json, str):
                                column_names = json.loads(cols_json)
                            elif isinstance(cols_json, list):
                                column_names = list(cols_json)

        finally:
            conn.close()

        # Fallback: build generic names if DB didn't provide them
        if not column_names and vectors_raw:
            column_names = [f"feat_{i}" for i in range(len(vectors_raw[0]))]

        # ------------------------------------------------------------------
        # Compute raw future returns
        # ------------------------------------------------------------------
        horizon = self.data_config.prediction_horizon
        if len(closes) <= horizon:
            raise ValueError(f"Insufficient data for horizon {horizon}")

        closes_arr = np.array(closes, dtype=np.float64)
        # Future price at t+horizon
        future_prices = closes_arr[horizon:]
        current_prices = closes_arr[:-horizon]

        # Percentage returns: (future - now) / now
        returns = (future_prices - current_prices) / (current_prices + 1e-10)

        # Optional clipping to reduce outliers
        if self.clip_returns is not None:
            returns = np.clip(returns, -self.clip_returns, self.clip_returns)

        # Optional standardization (fit on this split if mean/std not provided)
        if self.normalize_returns:
            if self.mean is None:
                self.mean = returns.mean()
            if self.std is None:
                self.std = returns.std() + 1e-8
            returns = (returns - self.mean) / self.std
            logger.info(f"  Returns standardized: mean={self.mean:.6f}, std={self.std:.6f}")

        # Align vectors/timestamps: discard last `horizon` rows (no future return)
        vectors_np = np.vstack(vectors_raw)
        X = vectors_np[:-horizon].astype(np.float32)
        y = returns.astype(np.float32)
        timestamps = timestamps[:-horizon]

        # Final NaN/inf sanitisation (defensive)
        if not np.isfinite(X).all():
            logger.warning("NaN/inf detected in feature matrix — replacing with 0")
            X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        if not np.isfinite(y).all():
            logger.warning("NaN/inf detected in targets — replacing with 0")
            y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)

        # Optional stride to reduce autocorrelation
        if self.return_stride > 1:
            X = X[:: self.return_stride]
            y = y[:: self.return_stride]
            timestamps = timestamps[:: self.return_stride]

        # Optional feature normalization (same as WideVectorDataset)
        if self.mean is not None and self.std is not None and self.feature_mask is not None:
            # ``mean``/``std`` refer to feature stats if they came from training set.
            # If they are return stats from above they are scalars — skip feature norm.
            if isinstance(self.mean, np.ndarray) and isinstance(self.std, np.ndarray):
                X = (X - self.mean) / self.std
                X = np.clip(X, -10.0, 10.0)  # defensive clip for near-zero-std features

        # Convert to list of rows for Dataset __getitem__ compatibility
        vectors_out = [X[i] for i in range(len(X))]
        targets_out = y.tolist()

        return vectors_out, targets_out, timestamps, column_names

    # ------------------------------------------------------------------
    # Dataset protocol
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.vectors)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Returns:
            x: (seq_len, input_dim) — a single vector (no temporal stacking here;
               the training collate will build sequences if needed).
            y: scalar target return.
        """
        # NOTE: ``seq_len`` handling is done in the training script via
        # a custom collate function that creates sliding windows.
        # For simplicity we return a single timestep here; the trainer
        # will build sequences by stacking consecutive rows.
        x = torch.from_numpy(self.vectors[idx]).float()
        y = torch.tensor(self.targets[idx], dtype=torch.float32)
        return x, y


def build_sequences(
    dataset: TradingDataset,
    sequence_length: int,
) -> List[Tuple[torch.Tensor, torch.Tensor]]:
    """
    Convert a flat TradingDataset into a list of (sequence, target) pairs.

    Args:
        dataset: A TradingDataset instance (already loaded).
        sequence_length: Number of consecutive timesteps per input sequence.
                         Target is the return at the final timestep.

    Returns:
        List of (seq, target) where seq is (sequence_length, input_dim).
    """
    vectors = dataset.vectors  # List[np.ndarray]
    targets = dataset.targets
    n = len(vectors)

    if n < sequence_length:
        raise ValueError(f"Dataset length {n} < sequence_length {sequence_length}")

    sequences = []
    for i in range(n - sequence_length + 1):
        seq = np.stack(vectors[i : i + sequence_length])  # (seq_len, feat)
        target = targets[i + sequence_length - 1]         # return at final step
        sequences.append((torch.from_numpy(seq).float(), torch.tensor(target, dtype=torch.float32)))

    logger.info(f"Built {len(sequences)} sequences of length {sequence_length}")
    return sequences
