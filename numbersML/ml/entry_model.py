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
        self.feature_mask = None
        self.profit_target = None
        self.stop_loss = None
        self.threshold: float = 0.5  # learned during train()

    @staticmethod
    def default_params() -> dict:
        """Optimized default parameters for time series classification.

        Notes:
            scale_pos_weight is intentionally absent here — it is computed
            dynamically from the training labels inside train() so it reflects
            the actual class ratio of the dataset.
        """
        return {
            'objective': 'binary',
            'metric': ['binary_logloss', 'auc'],
            'boosting_type': 'gbdt',
            'num_leaves': 63,
            'max_depth': -1,
            'learning_rate': 0.01,
            'feature_fraction': 0.8,
            'bagging_fraction': 0.8,
            'bagging_freq': 5,
            'verbose': -1,
            'random_state': 42,
            'min_child_samples': 50,
            'lambda_l1': 0.1,
            'lambda_l2': 0.1,
        }

    @staticmethod
    def find_best_threshold(
        y_true: np.ndarray, probs: np.ndarray
    ) -> Tuple[float, float]:
        """Find the probability threshold that maximises F1 on a validation set.

        Args:
            y_true: Binary ground-truth labels (0 / 1).
            probs:  Model output probabilities in [0, 1].

        Returns:
            best_threshold: Threshold value that maximises F1.
            best_f1:        Corresponding F1 score.
        """
        thresholds = np.linspace(0.01, 0.5, 100)
        best_f1 = 0.0
        best_t = 0.5

        for t in thresholds:
            preds = (probs >= t).astype(int)
            score = f1_score(y_true, preds, zero_division="warn")  # type: ignore[call-arg]
            if score > best_f1:
                best_f1 = score
                best_t = float(t)

        return best_t, best_f1

    @staticmethod
    def precision_at_k(y_true: np.ndarray, probs: np.ndarray, k: int) -> float:
        """Fraction of positives among the top-k highest-confidence predictions.

        Args:
            y_true: Binary ground-truth labels.
            probs:  Model output probabilities.
            k:      Number of top predictions to inspect.

        Returns:
            Precision among the k highest-probability samples.
        """
        k = min(k, len(probs))
        top_idx = np.argsort(probs)[-k:]
        return float(y_true[top_idx].mean())

    @staticmethod
    def expected_value(
        y_true: np.ndarray,
        probs: np.ndarray,
        threshold: float,
        profit: float,
        stop: float,
    ) -> float:
        """Estimate total expected value of trades triggered by `threshold`.

        Args:
            y_true:    Binary ground-truth labels.
            probs:     Model output probabilities.
            threshold: Decision boundary for taking a trade.
            profit:    Dollar (or %) gain per winning trade.
            stop:      Dollar (or %) loss per losing trade (positive number).

        Returns:
            Total expected value across all triggered trades.
        """
        preds = probs >= threshold
        wins = int(((y_true == 1) & preds).sum())
        losses = int(((y_true == 0) & preds).sum())
        return wins * profit - losses * stop

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray
    ) -> dict:
        """Train the model with early stopping."""

        y_val_binary = (y_val >= 0.5).astype(int)
        y_train_binary = (y_train >= 0.5).astype(int)

        # Dynamic class weighting — reflects the actual label ratio in this dataset.
        pos = int(np.sum(y_train_binary == 1))
        neg = int(np.sum(y_train_binary == 0))
        self.params['scale_pos_weight'] = neg / pos if pos > 0 else 1.0

        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

        logger.info("Training EntryPoint Model:")
        logger.info(f"  Train samples:      {X_train.shape[0]}")
        logger.info(f"  Val samples:        {X_val.shape[0]}")
        logger.info(f"  Features:           {X_train.shape[1]}")
        logger.info(f"  Pos/Neg (train):    {pos}/{neg}")
        logger.info(f"  scale_pos_weight:   {self.params['scale_pos_weight']:.2f}")

        self.model = lgb.train(
            self.params,
            train_data,
            num_boost_round=500,
            valid_sets=[val_data],
            callbacks=[
                lgb.log_evaluation(period=50),
                lgb.early_stopping(stopping_rounds=50),
            ],
        )

        # --- Evaluation ---
        val_pred: np.ndarray = np.asarray(
            self.model.predict(X_val, num_iteration=self.model.best_iteration)
        )

        # Learn the threshold that maximises F1 instead of using a hardcoded value.
        best_t, best_f1 = self.find_best_threshold(y_val_binary, val_pred)
        self.threshold = best_t
        val_pred_class = (val_pred >= self.threshold).astype(int)

        metrics = {
            'accuracy': accuracy_score(y_val_binary, val_pred_class),
            'precision': precision_score(y_val_binary, val_pred_class, zero_division="warn"),  # type: ignore[call-arg]
            'recall': recall_score(y_val_binary, val_pred_class, zero_division="warn"),  # type: ignore[call-arg]
            'f1': best_f1,
            'roc_auc': roc_auc_score(y_val_binary, val_pred),
            'best_iteration': self.model.best_iteration,
            'threshold': self.threshold,
        }

        logger.info("Training complete:")
        logger.info(f"  Best iteration: {metrics['best_iteration']}")
        logger.info(f"  Threshold (F1): {self.threshold:.4f}")
        logger.info(f"  Accuracy:       {metrics['accuracy']:.4f}")
        logger.info(f"  Precision:      {metrics['precision']:.4f}")
        logger.info(f"  Recall:         {metrics['recall']:.4f}")
        logger.info(f"  F1 Score:       {metrics['f1']:.4f}")
        logger.info(f"  ROC AUC:        {metrics['roc_auc']:.4f}")

        cm = confusion_matrix(y_val_binary, val_pred_class)
        logger.info("Confusion Matrix:")
        logger.info(f"  [[TN: {cm[0][0]}, FP: {cm[0][1]}]]")
        logger.info(f"  [[FN: {cm[1][0]}, TP: {cm[1][1]}]]")

        # Ranking-based evaluation — how good are the top signals?
        logger.info("Precision@K (ranking quality of top predictions):")
        for k in [100, 500, 1000, 5000]:
            p_at_k = self.precision_at_k(y_val_binary, val_pred, k)
            metrics[f'precision_at_{k}'] = p_at_k
            logger.info(f"  P@{k:>5}: {p_at_k:.4f}")

        # Trading-aware expected value (requires profit_target / stop_loss to be set).
        if self.profit_target is not None and self.stop_loss is not None:
            ev = self.expected_value(
                y_val_binary, val_pred, self.threshold, self.profit_target, self.stop_loss
            )
            metrics['expected_value'] = ev
            logger.info(f"  Expected value @ threshold {self.threshold:.4f}: {ev:.4f}")

        # Top-20 features by gain importance.
        gain, _ = self.get_feature_importance()
        top_idx = np.argsort(gain)[-20:]
        logger.info("Top-20 features by gain:")
        for i in reversed(top_idx):
            name = self.feature_names[i] if self.feature_names else str(i)
            logger.info(f"  [{i:>4}] {name}: {gain[i]:.2f}")

        return metrics

    def predict(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Predict entry probability for given features.

        Uses the threshold learned during training (``self.threshold``).

        Args:
            X: Feature matrix of shape ``(n_samples, n_features)``.

        Returns:
            probs:   Raw model probabilities in [0, 1], shape ``(n_samples,)``.
            classes: Binary predictions (0 / 1) thresholded at ``self.threshold``.
        """
        if self.model is None:
            raise ValueError("Model not trained")

        probs: np.ndarray = np.asarray(
            self.model.predict(X, num_iteration=self.model.best_iteration, predict_disable_shape_check=True)
        )
        classes: np.ndarray = (probs >= self.threshold).astype(int)
        return probs, classes

    def get_feature_importance(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return feature importance scores."""
        if self.model is None:
            raise ValueError("Model not trained")

        gain = self.model.feature_importance(importance_type='gain')
        split = self.model.feature_importance(importance_type='split')

        return gain, split

    def save(self, path: str, feature_mask: Optional[np.ndarray] = None) -> None:
        """Save model and associated metadata to a pickle file.

        Args:
            path: Destination file path.
            feature_mask: Optional boolean/index mask used during inference.
        """
        with open(path, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'params': self.params,
                'feature_names': self.feature_names,
                'feature_mask': feature_mask,
                'profit_target': self.profit_target,
                'stop_loss': self.stop_loss,
                'threshold': self.threshold,
            }, f)
        logger.info(f"Model saved to {path}")

    @classmethod
    def load(cls, path: str) -> 'EntryPointModel':
        """Load model and metadata from a pickle file.

        Args:
            path: Source file path produced by :meth:`save`.

        Returns:
            Fully initialised :class:`EntryPointModel` instance.
        """
        with open(path, 'rb') as f:
            data = pickle.load(f)

        instance = cls(data['params'])
        instance.model = data['model']
        instance.feature_names = data['feature_names']
        instance.profit_target = data.get('profit_target')
        instance.stop_loss = data.get('stop_loss')
        instance.feature_mask = data.get('feature_mask', None)
        instance.threshold = data.get('threshold', 0.5)  # backwards-compatible default

        logger.info(f"Model loaded from {path} (threshold={instance.threshold:.4f})")
        return instance
