"""
PyTorch Dataset for loading wide_vectors + target_values.

Data flow:
  wide_vectors.vector (JSONB array) -> X features
  candles_1s.target_value           -> Y target

The dataset handles:
  - Loading data from PostgreSQL
  - Creating sequences of consecutive wide_vectors for temporal context
  - Normalization (mean/std computed on training set)
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
        self.target_symbol = data_config.target_symbol

        # Load data
        self.vectors, self.targets, self.timestamps = self._load_data()

        # Compute normalization params if not provided
        if self.mean is None or self.std is None:
            all_vectors = np.vstack(self.vectors)
            self.mean = np.mean(all_vectors, axis=0)
            self.std = np.std(all_vectors, axis=0) + 1e-8
            
            # Filter out low-variance features (std < 0.01)
            # These features provide no information for learning
            min_std = 0.01
            self.feature_mask = self.std >= min_std
            n_features = self.feature_mask.sum()
            logger.info(f"Filtering features: {n_features}/{len(self.std)} kept (std >= {min_std})")
            
            # Apply mask to mean and std
            self.mean = self.mean[self.feature_mask]
            self.std = self.std[self.feature_mask]
        else:
            # If mean/std provided, use the provided feature_mask
            self.feature_mask = feature_mask if feature_mask is not None else np.ones(len(self.mean), dtype=bool)

        # Normalize vectors (only keep informative features)
        self.vectors = [(v[self.feature_mask] - self.mean) / self.std for v in self.vectors]

        # Build valid sequence indices
        self._build_sequences()

    def _load_data(
        self,
    ) -> Tuple[List[np.ndarray], List[float], List[datetime]]:
        """Load wide_vectors and target_values for a specific symbol."""
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

                # Load wide_vectors joined with target_values for THIS symbol only
                query = """
                    SELECT
                        wv.time,
                        wv.vector,
                        wv.vector_size,
                        c.target_value
                    FROM wide_vectors wv
                    LEFT JOIN candles_1s c ON c.time = wv.time AND c.symbol_id = %s
                    WHERE wv.time >= %s AND wv.time < %s
                      AND wv.vector_size >= 50
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

                        # Skip if target is None
                        if target is None:
                            continue

                        vectors.append(vec)
                        targets.append(float(target))
                        timestamps.append(ts)

        finally:
            conn.close()

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
                JOIN candles_1s c ON c.time = wv.time
                WHERE c.target_value IS NOT NULL
            """)
            row = cur.fetchone()
            if row and row[0] and row[1]:
                data_start = row[0]
                data_end = row[1]
            else:
                raise ValueError("No data available with target values")
    finally:
        conn.close()
    
    # Calculate time ranges based on available data
    data_hours = (data_end - data_start).total_seconds() / 3600
    logger.info(f"Available data: {data_start} to {data_end} ({data_hours:.2f} hours)")
    
    # Split proportionally: 70% train, 15% val, 15% test
    # Use actual available data, not config hours
    train_frac, val_frac, test_frac = 0.7, 0.15, 0.15
    
    total_seconds = (data_end - data_start).total_seconds()
    train_seconds = total_seconds * train_frac
    val_seconds = total_seconds * val_frac
    test_seconds = total_seconds * test_frac
    
    # Time ranges (going backwards from data_end)
    test_end = data_end
    test_start = data_end - timedelta(seconds=test_seconds)

    val_end = test_start
    val_start = val_end - timedelta(seconds=val_seconds)

    train_end = val_start
    train_start = data_start  # Use all remaining data for training

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
