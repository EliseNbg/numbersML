"""
PyTorch Dataset for loading wide_vectors + target_values.

Data flow:
  wide_vectors were calculated and stored in DB.
  candles_1s.target_value (JSONB) contains 'normalized_value' (0 to 1).
  We load this pre-calculated target directly.

The dataset handles:
  - Loading data from PostgreSQL
  - Loading pre-calculated normalized targets (0-1) from DB
  - Aligning X (wide vectors) with Y (future normalized value)
  - Feature normalization (StandardScaler)
  - Train/val/test splitting by time
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
import psycopg2

from ml.config import DatabaseConfig, DataConfig

logger = logging.getLogger(__name__)


class WideVectorDataset(Dataset):
    """
    Dataset that loads wide_vectors and corresponding target_values.

    Each sample is a sequence of `sequence_length` consecutive wide_vectors,
    with the target being the target_value for a SPECIFIC SYMBOL at the end of the sequence.

    Important:
    - wide_vector contains ALL symbols' data at timestamp T
    - target_value is for ONE specific symbol (e.g., BTC/USDC)
    - We train a model to predict THAT symbol's target from the wide vector
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
        sequence_length: int = 60,
    ):
        self.db_config = db_config
        self.data_config = data_config
        self.start_time = start_time
        self.end_time = end_time
        self.sequence_length = sequence_length
        self.mean = mean
        self.std = std
        self.feature_mask = feature_mask
        self.target_symbol = data_config.target_symbol

        # Load data
        self.vectors, self.targets, self.timestamps = self._load_data()

        # Compute normalization params if not provided
        if self.mean is None or self.std is None:
            all_vectors = np.vstack(self.vectors)
            
            # Apply StandardScaler: zero mean, unit variance
            self.mean = np.mean(all_vectors, axis=0)
            self.std = np.std(all_vectors, axis=0)
            
            # Add epsilon to prevent division by zero
            epsilon = 1e-8
            self.std = np.where(self.std < epsilon, epsilon, self.std)

            # Filter out low-variance features (std < 1e-6)
            # Using a lower threshold to keep valid features for low-priced assets (like ADA, DOGE)
            # and small indicator values that were previously being removed.
            min_std = 1e-6
            self.feature_mask = self.std > min_std
            
            # Apply feature mask
            self.mean = self.mean[self.feature_mask]
            self.std = self.std[self.feature_mask]
            
            # Normalize vectors: x = (x - mean) / std
            self.vectors = [(v[self.feature_mask] - self.mean) / self.std for v in self.vectors]
            
            print(f'Feature normalization: StandardScaler (zero mean, unit variance)')
            print(f'  Original features: {all_vectors.shape[1]}')
            print(f'  Features after mask: {len(self.mean)} (removed {all_vectors.shape[1] - len(self.mean)} low-variance)')
        else:
            # Apply existing feature mask and normalization
            self.vectors = [(v[self.feature_mask] - self.mean) / self.std for v in self.vectors]

        # Build valid sequence indices
        self._build_sequences()

    def _load_data(
        self,
    ) -> Tuple[List[np.ndarray], List[float], List[datetime]]:
        """Load wide_vectors and targets directly from DB."""
        conn = psycopg2.connect(
            host=self.db_config.host,
            port=self.db_config.port,
            dbname=self.db_config.dbname,
            user=self.db_config.user,
            password=self.db_config.password,
        )

        try:
            # First, get the symbol_id for the target symbol
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM symbols WHERE symbol = %s",
                    (self.target_symbol,)
                )
                symbol_row = cur.fetchone()
                if not symbol_row:
                    raise ValueError(f"Symbol '{self.target_symbol}' not found in database")
                symbol_id = symbol_row[0]

            # Now load data with a named cursor
            with conn.cursor(name="ml_data_cursor") as cur:
                cur.itersize = 5000

                # Load wide_vectors and pre-calculated normalized targets
                # We extract normalized_value from candles_1s.target_value (JSONB)
                query = """
                    SELECT
                        wv.time,
                        wv.vector,
                        wv.vector_size,
                        (c.target_value->>'normalized_value')::float AS target
                    FROM wide_vectors wv
                    JOIN candles_1s c ON c.time = wv.time AND c.symbol_id = %s
                    WHERE wv.time >= %s AND wv.time < %s
                      AND wv.vector_size >= 50
                      AND c.target_value IS NOT NULL
                      AND (c.target_value->>'normalized_value') IS NOT NULL
                    ORDER BY wv.time
                """
                cur.execute(query, (symbol_id, self.start_time, self.end_time))

                vectors = []
                targets = []
                timestamps = []
                prev_size = None

                while True:
                    rows = cur.fetchmany(5000)
                    if not rows:
                        break

                    for row in rows:
                        ts, vector_json, vec_size, target = row

                        # Parse vector from JSONB
                        if isinstance(vector_json, str):
                            vec = np.array(json.loads(vector_json), dtype=np.float32)
                        else:
                            vec = np.array(vector_json, dtype=np.float32)

                        # Handle variable-length vectors by padding
                        if prev_size is None:
                            prev_size = len(vec)
                        elif len(vec) != prev_size:
                            # Pad shorter vectors with zeros
                            if len(vec) < prev_size:
                                vec = np.pad(vec, (0, prev_size - len(vec)))
                            else:
                                vec = vec[:prev_size]

                        vectors.append(vec)
                        targets.append(float(target))
                        timestamps.append(ts)

        finally:
            conn.close()

        # Align X (wide vectors at time t) with Y (target at time t + horizon)
        horizon = self.data_config.prediction_horizon
        if len(targets) > horizon:
            targets = targets[horizon:]
            vectors = vectors[:-horizon]
            timestamps = timestamps[:-horizon]
        else:
            raise ValueError(f"Not enough data for prediction horizon {horizon}")

        print(f'Loaded {len(vectors)} samples, {len(targets)} targets, {len(timestamps)} timestamps')
        print(f'  Symbol: {self.target_symbol}, target id: {symbol_id}')
        print(f'  Time range: {timestamps[0] if timestamps else "N/A"} to {timestamps[-1] if timestamps else "N/A"}')
        print(f'  Prediction horizon: {horizon}')

        if len(vectors) < self.data_config.min_samples:
            raise ValueError(
                f"Insufficient samples: {len(vectors)} < {self.data_config.min_samples}"
            )

        return vectors, targets, timestamps

    def _build_sequences(self):
        """Build valid sequence start indices."""
        self.sequence_indices = []
        n = len(self.vectors)

        for i in range(n - self.sequence_length + 1):
            # Check if timestamps are consecutive (allow 1-2 second gaps)
            start_ts = self.timestamps[i]
            end_ts = self.timestamps[i + self.sequence_length - 1]
            expected_duration = timedelta(seconds=self.sequence_length - 1)
            actual_duration = end_ts - start_ts

            # Allow small gaps (up to 5 seconds)
            if actual_duration <= expected_duration + timedelta(seconds=5):
                self.sequence_indices.append(i)

    def __len__(self) -> int:
        return len(self.sequence_indices)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        start_idx = self.sequence_indices[idx]
        end_idx = start_idx + self.sequence_length

        # Stack vectors into (sequence_length, features)
        sequence = np.stack(self.vectors[start_idx:end_idx])

        # Target is the target_value at the end of the sequence
        target = self.targets[end_idx - 1]

        return torch.from_numpy(sequence), torch.tensor(target, dtype=torch.float32)

    def get_feature_dim(self) -> int:
        """Get the feature dimension of the vectors."""
        return len(self.vectors[0]) if self.vectors else 0


def create_data_loaders(
    db_config: DatabaseConfig,
    data_config: DataConfig,
) -> Tuple[DataLoader, DataLoader, DataLoader, np.ndarray, np.ndarray, np.ndarray]:
    """
    Create train, validation, and test data loaders.

    Returns:
        train_loader, val_loader, test_loader, mean, std, feature_mask
    """
    # First, check what data is available
    conn = psycopg2.connect(
        host=db_config.host,
        port=db_config.port,
        dbname=db_config.dbname,
        user=db_config.user,
        password=db_config.password,
    )
    
    try:
        with conn.cursor() as cur:
            # Get the actual data range available
            cur.execute("""
                SELECT 
                    MIN(wv.time) as earliest,
                    MAX(wv.time) as latest
                FROM wide_vectors wv
                INNER JOIN candles_1s c ON c.time = wv.time AND c.symbol_id = (
                    SELECT id FROM symbols WHERE symbol = %s
                )
                WHERE c.close IS NOT NULL
            """, (data_config.target_symbol,))
            row = cur.fetchone()
            if row and row[0] and row[1]:
                data_start = row[0]
                data_end = row[1]
            else:
                raise ValueError("No data available with target values")
    finally:
        conn.close()
    
    # Calculate time ranges based on available data and user request
    data_hours = (data_end - data_start).total_seconds() / 3600
    logger.info(f"Available data: {data_start} to {data_end} ({data_hours:.2f} hours)")

    # Check if user requested a specific time window (train_hours)
    # If train_hours is set and smaller than available data, we respect it
    # by shifting the end time to 'now' (or data_end) and start time backwards.
    
    # Default split: 70% train, 15% val, 15% test
    train_frac, val_frac, test_frac = 0.7, 0.15, 0.15

    # Determine the effective time window
    # If train_hours is defined in config (and > 0), we use it to limit the range
    requested_hours = data_config.train_hours
    
    if requested_hours > 0:
        # Use the requested hours starting from the latest data point
        total_requested_seconds = requested_hours * 3600
        
        # Ensure we don't go beyond available data
        effective_start = max(data_start, data_end - timedelta(seconds=total_requested_seconds))
        
        # If the requested window is larger than available data, use all data
        if (data_end - effective_start).total_seconds() <= 0:
            effective_start = data_start
            
        total_seconds = (data_end - effective_start).total_seconds()
        logger.info(f"Using requested window: {requested_hours} hours (Effective: {total_seconds/3600:.2f}h)")
    else:
        # Use all available data
        total_seconds = (data_end - data_start).total_seconds()
        effective_start = data_start
        logger.info(f"Using all available data: {total_seconds/3600:.2f} hours")

    # Calculate split durations
    train_seconds = total_seconds * train_frac
    val_seconds = total_seconds * val_frac
    test_seconds = total_seconds * test_frac

    # Time ranges (going backwards from data_end)
    test_end = data_end
    test_start = data_end - timedelta(seconds=test_seconds)

    val_end = test_start
    val_start = val_end - timedelta(seconds=val_seconds)

    train_end = val_start
    train_start = effective_start  # Start from the effective beginning

    logger.info(f"Train: {train_start} to {train_end}")
    logger.info(f"Val:   {val_start} to {val_end}")
    logger.info(f"Test:  {test_start} to {test_end}")

    # Load training data first to compute normalization
    train_dataset = WideVectorDataset(
        db_config=db_config,
        data_config=data_config,
        start_time=train_start,
        end_time=train_end,
        sequence_length=data_config.sequence_length,
    )

    mean = train_dataset.mean
    std = train_dataset.std
    feature_mask = train_dataset.feature_mask

    # Load val and test with training normalization and feature mask
    val_dataset = WideVectorDataset(
        db_config=db_config,
        data_config=data_config,
        start_time=val_start,
        end_time=val_end,
        mean=mean,
        std=std,
        feature_mask=feature_mask,
        sequence_length=data_config.sequence_length,
    )

    test_dataset = WideVectorDataset(
        db_config=db_config,
        data_config=data_config,
        start_time=test_start,
        end_time=test_end,
        mean=mean,
        std=std,
        feature_mask=feature_mask,
        sequence_length=data_config.sequence_length,
    )

    train_loader = DataLoader(
        train_dataset,
        batch_size=data_config.batch_size,
        shuffle=True,
        num_workers=data_config.num_workers,
        pin_memory=False,
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=data_config.batch_size,
        shuffle=False,
        num_workers=data_config.num_workers,
        pin_memory=False,
    )

    test_loader = DataLoader(
        test_dataset,
        batch_size=data_config.batch_size,
        shuffle=False,
        num_workers=data_config.num_workers,
        pin_memory=False,
    )

    logger.info(f"Train samples: {len(train_dataset)}")
    logger.info(f"Val samples:   {len(val_dataset)}")
    logger.info(f"Test samples:  {len(test_dataset)}")
    logger.info(f"Feature dim:   {train_dataset.get_feature_dim()}")

    return train_loader, val_loader, test_loader, mean, std, feature_mask
