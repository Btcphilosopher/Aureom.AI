"""
Modular ML layer (spec items 45-47): quality-rejection prediction and
predictive-maintenance failure-probability prediction, trained on
*simulated* historical factory data.

IMPORTANT (spec item 45): simulated telemetry is not equivalent to
validated industrial data. Every model here is fit against this
platform's own process simulators, so it demonstrates the pipeline
(features -> train -> predict -> feature importance) rather than
delivering a production-validated model. Swap in real historical data
through the same interface once it exists.

Uses scikit-learn when available (better-calibrated RandomForest models);
otherwise falls back to a from-scratch numpy logistic-regression trained by
gradient descent, so the platform has no hard ML dependency.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    from sklearn.ensemble import RandomForestClassifier
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False


@dataclass
class TrainedModelSummary:
    feature_names: list[str]
    feature_importance: dict[str, float]
    train_accuracy: float
    backend: str
    data_provenance: str = "simulated_telemetry -- NOT validated industrial data"


class _NumpyLogisticRegression:
    """From-scratch fallback: standardised features, gradient-descent logistic regression."""

    def __init__(self, lr: float = 0.1, epochs: int = 500, l2: float = 1e-3) -> None:
        self.lr, self.epochs, self.l2 = lr, epochs, l2
        self.weights: np.ndarray | None = None
        self.bias: float = 0.0
        self.mean: np.ndarray | None = None
        self.std: np.ndarray | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self.mean, self.std = X.mean(axis=0), X.std(axis=0) + 1e-9
        Xs = (X - self.mean) / self.std
        n, d = Xs.shape
        self.weights = np.zeros(d)
        for _ in range(self.epochs):
            z = Xs @ self.weights + self.bias
            p = 1.0 / (1.0 + np.exp(-z))
            grad_w = Xs.T @ (p - y) / n + self.l2 * self.weights
            grad_b = float(np.mean(p - y))
            self.weights -= self.lr * grad_w
            self.bias -= self.lr * grad_b

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        Xs = (X - self.mean) / self.std
        z = Xs @ self.weights + self.bias
        return 1.0 / (1.0 + np.exp(-z))

    def feature_importance(self) -> np.ndarray:
        return np.abs(self.weights) / (np.sum(np.abs(self.weights)) + 1e-9)


class QualityPredictionModel:
    """Predicts probability of cell rejection from process variables
    (coating, calendering, moisture, formation, temperature, machine
    condition) and reports feature importance (spec item 46)."""

    def __init__(self) -> None:
        self.model = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=0) if _HAS_SKLEARN else _NumpyLogisticRegression()
        self.feature_names: list[str] = []
        self.backend = "sklearn.RandomForestClassifier" if _HAS_SKLEARN else "numpy_logistic_regression"

    def train(self, X: np.ndarray, y: np.ndarray, feature_names: list[str]) -> TrainedModelSummary:
        self.feature_names = feature_names
        self.model.fit(X, y)
        preds = self.predict(X) >= 0.5
        accuracy = float(np.mean(preds == y.astype(bool)))

        if _HAS_SKLEARN:
            importances = self.model.feature_importances_
        else:
            importances = self.model.feature_importance()

        return TrainedModelSummary(
            feature_names=feature_names,
            feature_importance=dict(zip(feature_names, importances.tolist())),
            train_accuracy=accuracy,
            backend=self.backend,
        )

    def predict(self, X: np.ndarray) -> np.ndarray:
        if _HAS_SKLEARN:
            return self.model.predict_proba(X)[:, 1]
        return self.model.predict_proba(X)


class PredictiveMaintenanceModel:
    """Predicts near-term failure probability from telemetry features
    (vibration, temperature, runtime, current, historical faults)."""

    def __init__(self) -> None:
        self.model = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=0) if _HAS_SKLEARN else _NumpyLogisticRegression()
        self.feature_names: list[str] = []
        self.backend = "sklearn.RandomForestClassifier" if _HAS_SKLEARN else "numpy_logistic_regression"

    def train(self, X: np.ndarray, y: np.ndarray, feature_names: list[str]) -> TrainedModelSummary:
        self.feature_names = feature_names
        self.model.fit(X, y)
        preds = self.predict(X) >= 0.5
        accuracy = float(np.mean(preds == y.astype(bool)))
        importances = self.model.feature_importances_ if _HAS_SKLEARN else self.model.feature_importance()
        return TrainedModelSummary(
            feature_names=feature_names,
            feature_importance=dict(zip(feature_names, importances.tolist())),
            train_accuracy=accuracy,
            backend=self.backend,
        )

    def predict(self, X: np.ndarray) -> np.ndarray:
        if _HAS_SKLEARN:
            return self.model.predict_proba(X)[:, 1]
        return self.model.predict_proba(X)


def synthesize_quality_training_data(n: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Builds a simulated (not real) training set linking process variables to
    a rejection label, using the same causal directions as `production.coating`
    and `production.testing` (higher speed / poorer slurry / moisture -> more
    rejects), so the model has something structurally learnable to find."""
    feature_names = ["line_speed_m_min", "coating_thickness_um", "calendering_pressure_kn_m",
                      "moisture_pct", "formation_temp_c", "machine_vibration_mm_s"]
    speed = rng.uniform(15, 60, n)
    thickness = rng.normal(80, 8, n)
    pressure = rng.uniform(150, 450, n)
    moisture = rng.exponential(0.3, n)
    formation_temp = rng.normal(30, 6, n)
    vibration = rng.exponential(0.6, n)

    risk = (
        0.02 * (speed - 30) + 0.05 * np.abs(thickness - 80) + 0.01 * np.abs(pressure - 300) / 10
        + 0.8 * moisture + 0.05 * np.maximum(0, formation_temp - 40) + 0.6 * vibration
    )
    prob_reject = 1.0 / (1.0 + np.exp(-(risk - 2.0)))
    labels = (rng.random(n) < prob_reject).astype(int)

    X = np.column_stack([speed, thickness, pressure, moisture, formation_temp, vibration])
    return X, labels, feature_names
