"""
Dataset for Entry Point Classification Model.

Uses the new labeling logic instead of price prediction targets.
"""

import logging
import numpy as np
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

from ml.dataset import WideVectorDataset
from ml.entry_labeling import label_entry_points, filter_entry_samples


class EntryPointDataset(WideVectorDataset):
    """
    Dataset optimized for binary entry point classification.
    
    Overrides the target calculation logic to use entry point labeling
    instead of future price prediction.
    """
    
    def __init__(
        self,
        *args,
        profit_target: float = 0.005,
        stop_loss: float = 0.002,
        look_ahead: int = 1800,
        balance_classes: bool = True,
        **kwargs
    ):
        self.profit_target = profit_target
        self.stop_loss = stop_loss
        self.look_ahead = look_ahead
        self.balance_classes = balance_classes
        
        super().__init__(*args, **kwargs)
        
    def _load_data(self) -> Tuple[List[np.ndarray], List[float], List]:
        """Load data and apply entry point labeling."""
        vectors, _, timestamps = super()._load_data()
        
        # Get close prices from parent dataset
        closes = np.array(self.closes, dtype=np.float64)
        
        # Label entry points with actual parameters
        labels, scores = label_entry_points(
            closes,
            profit_target=self.profit_target,
            stop_loss=self.stop_loss,
            look_ahead=self.look_ahead
        )
        
        # Filter valid samples - align lengths (parent dataset truncates last look_ahead samples)
        vectors_np = np.vstack(vectors)
        valid_length = len(vectors_np)
        labels = labels[:valid_length]
        scores = scores[:valid_length]
        
        X, y = filter_entry_samples(vectors_np, labels, scores, balance_classes=self.balance_classes)
        
        # Store filtered data
        self.vectors = list(X)
        self.targets = list(y)
        self.timestamps = timestamps[:len(y)]
        
        pos = np.sum(y == 1)
        neg = np.sum(y == 0)
        
        logger.info(f"✅ Entry Point Label Stats:")
        logger.info(f"   Profit target: {self.profit_target*100:.2f}% | Stop loss: {self.stop_loss*100:.2f}%")
        logger.info(f"   Positiv: {pos} | Negativ: {neg} | Ratio: {(pos/len(y))*100:.1f}%")
        
        return self.vectors, self.targets, self.timestamps
