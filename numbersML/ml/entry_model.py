"""
Entry Point Classification Model using LightGBM.

This model performs binary classification:
Output: 0 = Bad entry, 1 = Good entry

LightGBM is used because:
  - 10x faster training than neural networks
  - Much better performance on tabular data
  - Built in handling for overfitting
  - No feature scaling required
  - Native probability output
"""

import logging
import pickle
from typing import Optional, Tuple

import numpy as np
import lightgbm as lgb
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix
)

logger = logging.getLogger(__name__)


class EntryPointModel:
    """Binary classifier for trading entry points."""

    def __init__(self, params: Optional[dict] = None):
        self.params = params or self.default_params()
        self.model = None
        self.feature_names = None

    @staticmethod
    def default_params() -> dict:
        """Optimized default parameters for time series classification."""
        return {
            'objective': 'binary',
            'metric': ['binary_logloss', 'auc'],
            'boosting_type': 'gbdt',
            'num_leaves': 15,
            'max_depth': 3,
            'learning_rate': 0.005,
            'feature_fraction': 0.8,
            'bagging_fraction': 0.9,
            'bagging_freq': 10,
            'verbose': -1,
            'random_state': 42,
            'is_unbalance': False,
            'scale_pos_weight': 1.2,
            'min_child_samples': 200,
            'min_split_gain': 0.001,
            'lambda_l1': 0.5,
            'lambda_l2': 0.5,
            'early_stopping_round': 15,
        }

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray
    ) -> dict:
        """Train the model with early stopping."""

        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

        logger.info(f"Training EntryPoint Model:")
        logger.info(f"  Train samples: {X_train.shape[0]}")
        logger.info(f"  Val samples:   {X_val.shape[0]}")
        logger.info(f"  Features:      {X_train.shape[1]}")

        self.model = lgb.train(
            self.params,
            train_data,
            num_boost_round=200,
            valid_sets=[val_data],
            callbacks=[lgb.log_evaluation(period=10)]
        )

        # Evaluate
        val_pred = self.model.predict(X_val, num_iteration=self.model.best_iteration)
        val_pred_class = (val_pred > 0.6).astype(int)
        y_val_binary = (y_val >= 0.5).astype(int)

        metrics = {
            'accuracy': accuracy_score(y_val_binary, val_pred_class),
            'precision': precision_score(y_val_binary, val_pred_class),
            'recall': recall_score(y_val_binary, val_pred_class),
            'f1': f1_score(y_val_binary, val_pred_class),
            'roc_auc': roc_auc_score(y_val_binary, val_pred),
            'best_iteration': self.model.best_iteration
        }

        logger.info(f"Training complete:")
        logger.info(f"  Best iteration: {metrics['best_iteration']}")
        logger.info(f"  Accuracy:  {metrics['accuracy']:.4f}")
        logger.info(f"  Precision: {metrics['precision']:.4f}")
        logger.info(f"  Recall:    {metrics['recall']:.4f}")
        logger.info(f"  F1 Score:  {metrics['f1']:.4f}")
        logger.info(f"  ROC AUC:   {metrics['roc_auc']:.4f}")

        logger.info(f"Confusion Matrix:")
        cm = confusion_matrix(y_val_binary, val_pred_class)
        logger.info(f"  [[TN: {cm[0][0]}, FP: {cm[0][1]}]]")
        logger.info(f"  [[FN: {cm[1][0]}, TP: {cm[1][1]}]]")

        return metrics

    def predict(self, X: np.ndarray, threshold: float = 0.9) -> Tuple[np.ndarray, np.ndarray]:
        """
        Predict entry probability for given features.

        Returns:
            probabilities: Raw model output [0..1]
            predictions: Binary class using threshold
        """
        if self.model is None:
            raise ValueError("Model not trained")

        probs = self.model.predict(X, num_iteration=self.model.best_iteration, predict_disable_shape_check=True)
        classes = (probs >= threshold).astype(int)

        return probs, classes

    def get_feature_importance(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return feature importance scores."""
        if self.model is None:
            raise ValueError("Model not trained")

        gain = self.model.feature_importance(importance_type='gain')
        split = self.model.feature_importance(importance_type='split')

        return gain, split

    def save(self, path: str, feature_mask = None) -> None:
        """Save model to file."""
        with open(path, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'params': self.params,
                'feature_names': self.feature_names,
                'feature_mask': feature_mask
            }, f)
        logger.info(f"Model saved to {path}")

    @classmethod
    def load(cls, path: str) -> 'EntryPointModel':
        """Load model from file."""
        with open(path, 'rb') as f:
            data = pickle.load(f)

        instance = cls(data['params'])
        instance.model = data['model']
        instance.feature_names = data['feature_names']
        instance.feature_mask = data.get('feature_mask', None)

        logger.info(f"Model loaded from {path}")
        return instance
