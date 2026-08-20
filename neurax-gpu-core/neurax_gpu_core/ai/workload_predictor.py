"""
Lightweight performance-prediction surrogate.

Used by :mod:`ai.gpu_tuner` to fit a cheap regression model over the
(architecture-knob -> objective-score) samples produced by the
:class:`~optimisation.architecture_optimizer.ArchitectureOptimizer`'s
search history, so future design-space exploration can be informed by an
interpolated estimate instead of always paying for a full simulation run.

Uses a small PyTorch MLP when torch is importable, and transparently falls
back to closed-form (numpy) ridge regression otherwise -- torch is an
optional dependency per the project spec.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

try:
    import torch
    import torch.nn as nn
    _TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when torch is absent
    _TORCH_AVAILABLE = False


@dataclass
class FitReport:
    backend: str
    n_samples: int
    train_r2: float


class _TinyMLP:  # pragma: no cover - only constructed when torch is present
    def __init__(self, in_features: int, hidden: int = 16):
        self.module = nn.Sequential(
            nn.Linear(in_features, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def fit(self, x: "torch.Tensor", y: "torch.Tensor", epochs: int = 300, lr: float = 0.02) -> None:
        opt = torch.optim.Adam(self.module.parameters(), lr=lr)
        loss_fn = nn.MSELoss()
        for _ in range(epochs):
            opt.zero_grad()
            pred = self.module(x).squeeze(-1)
            loss = loss_fn(pred, y)
            loss.backward()
            opt.step()

    def predict(self, x: "torch.Tensor") -> "torch.Tensor":
        with torch.no_grad():
            return self.module(x).squeeze(-1)


class PerformancePredictor:
    """Fits ``score = f(feature_vector)`` from architecture-search samples."""

    def __init__(self, prefer_torch: bool = True, ridge_lambda: float = 1e-2):
        self.use_torch = prefer_torch and _TORCH_AVAILABLE
        self.ridge_lambda = ridge_lambda
        self._fitted = False
        self._feature_mean: Optional[np.ndarray] = None
        self._feature_std: Optional[np.ndarray] = None
        self._weights: Optional[np.ndarray] = None
        self._torch_model: Optional[_TinyMLP] = None
        self.last_fit_report: Optional[FitReport] = None

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def _normalise(self, X: np.ndarray) -> np.ndarray:
        return (X - self._feature_mean) / self._feature_std

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> FitReport:
        X_arr = np.asarray(X, dtype=np.float64)
        y_arr = np.asarray(y, dtype=np.float64)
        if X_arr.ndim != 2 or len(X_arr) < 2:
            raise ValueError("PerformancePredictor.fit needs at least 2 samples of shape (n, d)")

        self._feature_mean = X_arr.mean(axis=0)
        self._feature_std = X_arr.std(axis=0)
        self._feature_std[self._feature_std < 1e-9] = 1.0
        Xn = self._normalise(X_arr)

        if self.use_torch:  # pragma: no cover - depends on optional torch
            self._torch_model = _TinyMLP(in_features=Xn.shape[1])
            x_t = torch.tensor(Xn, dtype=torch.float32)
            y_t = torch.tensor(y_arr, dtype=torch.float32)
            self._torch_model.fit(x_t, y_t)
            pred = self._torch_model.predict(x_t).numpy()
            backend = "torch_mlp"
        else:
            ones = np.ones((Xn.shape[0], 1))
            design = np.hstack([Xn, ones])
            reg = self.ridge_lambda * np.eye(design.shape[1])
            self._weights = np.linalg.solve(design.T @ design + reg, design.T @ y_arr)
            pred = design @ self._weights
            backend = "ridge_regression"

        ss_res = float(np.sum((y_arr - pred) ** 2))
        ss_tot = float(np.sum((y_arr - y_arr.mean()) ** 2)) or 1e-9
        r2 = 1.0 - ss_res / ss_tot

        self._fitted = True
        self.last_fit_report = FitReport(backend=backend, n_samples=len(y_arr), train_r2=r2)
        return self.last_fit_report

    def predict(self, X: Sequence[Sequence[float]]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("PerformancePredictor.predict called before fit()")
        X_arr = np.asarray(X, dtype=np.float64)
        Xn = self._normalise(X_arr)
        if self.use_torch:  # pragma: no cover
            x_t = torch.tensor(Xn, dtype=torch.float32)
            return self._torch_model.predict(x_t).numpy()
        ones = np.ones((Xn.shape[0], 1))
        design = np.hstack([Xn, ones])
        return design @ self._weights
