"""
Dataset for Entry Point Classification Model.

Uses the new labeling logic instead of price prediction targets.
"""

import numpy as np
from typing import Optional, Tuple, List

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
        vectors, targets, timestamps = super()._load_data()
        
        # Extract closes from vectors (we will get prices directly from DB separately)
        return vectors, targets, timestamps
        
        # Label entry points
        labels, scores = label_entry_points(
            closes,
            profit_target=self.profit_target,
            stop_loss=self.stop_loss,
            look_ahead=self.look_ahead
        )
        
        # Filter valid samples
        vectors_np = np.vstack(vectors)
        X, y = filter_entry_samples(vectors_np, labels, scores, balance_classes=self.balance_classes)
        
        # Store filtered data
        self.vectors = list(X)
        self.targets = list(y)
        self.timestamps = timestamps[:len(y)]
        
        print(f'Entry Point Dataset loaded:')
        print(f'  Total samples: {len(self.vectors)}')
        print(f'  Positive class: {np.sum(y == 1)} ({np.sum(y == 1)/len(y)*100:.1f}%)')
        print(f'  Negative class: {np.sum(y == 0)} ({np.sum(y == 0)/len(y)*100:.1f}%)')
        
        return self.vectors, self.targets, self.timestamps
