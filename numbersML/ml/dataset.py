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
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
import psycopg2
from psycopg2.extras import RealDictCursor

from ml.config import DatabaseConfig, DataConfig


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

        # Normalize vectors
        self.vectors = [(v - self.mean) / self.std for v in self.vectors]

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
) -> Tuple[DataLoader, DataLoader, DataLoader, np.ndarray, np.ndarray]:
    """
    Create train, validation, and test data loaders.

    Returns:
        train_loader, val_loader, test_loader, mean, std
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
                data_start = row[0].replace(tzinfo=None)
                data_end = row[1].replace(tzinfo=None)
            else:
                raise ValueError("No data available with target values")
    finally:
        conn.close()
    
    # Calculate time ranges based on available data
    data_hours = (data_end - data_start).total_seconds() / 3600
    print(f"Available data: {data_start} to {data_end} ({data_hours:.1f} hours)")
    
    # If data is limited, adjust proportions
    total_hours_needed = data_config.train_hours + data_config.val_hours + data_config.test_hours
    if data_hours < total_hours_needed:
        # Scale down proportionally
        scale = data_hours / total_hours_needed
        train_hours = int(data_config.train_hours * scale)
        val_hours = int(data_config.val_hours * scale)
        test_hours = int(data_config.test_hours * scale)
        
        # Ensure minimum hours
        train_hours = max(train_hours, 1)
        val_hours = max(val_hours, 1)
        test_hours = max(test_hours, 1)
    else:
        train_hours = data_config.train_hours
        val_hours = data_config.val_hours
        test_hours = data_config.test_hours
    
    # Time ranges (going backwards from data_end)
    test_end = data_end
    test_start = data_end - timedelta(hours=test_hours)

    val_end = test_start
    val_start = val_end - timedelta(hours=val_hours)

    train_end = val_start
    train_start = train_end - timedelta(hours=train_hours)
    
    # Ensure train_start is not before data_start
    if train_start < data_start:
        train_start = data_start

    print(f"Train: {train_start} to {train_end}")
    print(f"Val:   {val_start} to {val_end}")
    print(f"Test:  {test_start} to {test_end}")

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

    # Load val and test with training normalization
    val_dataset = WideVectorDataset(
        db_config=db_config,
        data_config=data_config,
        start_time=val_start,
        end_time=val_end,
        mean=mean,
        std=std,
        sequence_length=data_config.sequence_length,
    )

    test_dataset = WideVectorDataset(
        db_config=db_config,
        data_config=data_config,
        start_time=test_start,
        end_time=test_end,
        mean=mean,
        std=std,
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

    print(f"Train samples: {len(train_dataset)}")
    print(f"Val samples:   {len(val_dataset)}")
    print(f"Test samples:  {len(test_dataset)}")
    print(f"Feature dim:   {train_dataset.get_feature_dim()}")

    return train_loader, val_loader, test_loader, mean, std
