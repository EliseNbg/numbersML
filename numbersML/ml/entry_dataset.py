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
        vectors, targets, timestamps = super()._load_data()
        
        # ✅ Fix: Konvertiere kontinuierliche Targets in saubere binäre Labels 0/1
        # Alle Werte >= 0.8 werden als Positiv gewertet, Rest als Negativ
        binary_targets = [1.0 if t >= 0.8 else 0.0 for t in targets]
        
        pos = sum(1 for t in binary_targets if t == 1.0)
        neg = sum(1 for t in binary_targets if t == 0.0)
        
        logger.info(f"✅ Entry Point Label Stats:")
        logger.info(f"   Positiv: {pos} | Negativ: {neg} | Ratio: {(pos/len(targets))*100:.1f}%")
        
        return vectors, binary_targets, timestamps
        
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
