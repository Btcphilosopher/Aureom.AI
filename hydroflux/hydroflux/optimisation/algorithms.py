"""
Pluggable optimisation backends.

Every algorithm implements the same contract:

    result = algorithm.optimise(objective_fn, bounds, seed=42, maximize=True)

``objective_fn`` takes a 1-D array of decision variables and returns a
scalar. ``bounds`` is a list of ``(low, high)`` tuples, one per variable.
This lets :mod:`hydroflux.core.engine` (and any other caller) swap between
gradient-based local search, global metaheuristics, linear programming and
Monte Carlo / genetic / Bayesian search without changing the calling code --
only machine-learning where it earns its keep (surrogate-model search, not
decoration).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import numpy as np
from scipy.optimize import differential_evolution, linprog, minimize


@dataclass
class OptResult:
    best_x: np.ndarray
    best_value: float
    n_evaluations: int
    history: list[float] = field(default_factory=list)
    method: str = ""


class OptimisationAlgorithm(ABC):
    @abstractmethod
    def optimise(
        self,
        objective_fn: Callable[[np.ndarray], float],
        bounds: Sequence[tuple[float, float]],
        seed: Optional[int] = None,
        maximize: bool = True,
        **kwargs,
    ) -> OptResult:
        raise NotImplementedError


def _signed(objective_fn: Callable[[np.ndarray], float], maximize: bool) -> Callable[[np.ndarray], float]:
    return objective_fn if maximize else (lambda x: -objective_fn(x))


class ScipyMinimizeAlgorithm(OptimisationAlgorithm):
    """Local, gradient-free bounded search (Nelder-Mead / L-BFGS-B via
    finite differences). Fast, good for refining a solution found by a
    global search."""

    def __init__(self, method: str = "L-BFGS-B"):
        self.method = method

    def optimise(self, objective_fn, bounds, seed=None, maximize=True, x0=None, **kwargs) -> OptResult:
        rng = np.random.default_rng(seed)
        bounds = list(bounds)
        if x0 is None:
            x0 = np.array([rng.uniform(lo, hi) for lo, hi in bounds])
        history: list[float] = []

        def neg(x):
            value = objective_fn(x)
            history.append(value if maximize else -value)
            return -value if maximize else value

        result = minimize(neg, x0, method=self.method, bounds=bounds, **kwargs)
        best_value = -result.fun if maximize else result.fun
        return OptResult(best_x=np.asarray(result.x), best_value=float(best_value), n_evaluations=len(history), history=history, method="scipy_minimize")


class DifferentialEvolutionAlgorithm(OptimisationAlgorithm):
    """Global metaheuristic; the default choice for HydroFlux policy-search
    problems (non-smooth, few dimensions, cheap-ish objective evaluation)."""

    def __init__(self, maxiter: int = 25, popsize: int = 12, tol: float = 1e-4):
        self.maxiter = maxiter
        self.popsize = popsize
        self.tol = tol

    def optimise(self, objective_fn, bounds, seed=None, maximize=True, **kwargs) -> OptResult:
        history: list[float] = []

        def neg(x):
            value = objective_fn(x)
            history.append(value)
            return -value if maximize else value

        result = differential_evolution(
            neg, bounds=list(bounds), maxiter=self.maxiter, popsize=self.popsize, tol=self.tol, seed=seed, polish=True
        )
        best_value = -result.fun if maximize else result.fun
        return OptResult(best_x=np.asarray(result.x), best_value=float(best_value), n_evaluations=result.nfev, history=history, method="differential_evolution")


class MonteCarloSearchAlgorithm(OptimisationAlgorithm):
    """Uniform random search -- a transparent baseline, and the workhorse
    behind the Monte Carlo uncertainty engine when used for sampling rather
    than optimisation."""

    def __init__(self, n_samples: int = 500):
        self.n_samples = n_samples

    def optimise(self, objective_fn, bounds, seed=None, maximize=True, **kwargs) -> OptResult:
        rng = np.random.default_rng(seed)
        bounds = list(bounds)
        best_x, best_value = None, -np.inf if maximize else np.inf
        history = []
        for _ in range(self.n_samples):
            x = np.array([rng.uniform(lo, hi) for lo, hi in bounds])
            value = objective_fn(x)
            history.append(value)
            if (maximize and value > best_value) or (not maximize and value < best_value):
                best_x, best_value = x, value
        return OptResult(best_x=best_x, best_value=float(best_value), n_evaluations=self.n_samples, history=history, method="monte_carlo")


class GeneticAlgorithm(OptimisationAlgorithm):
    """A compact, dependency-free genetic algorithm: tournament selection,
    blend crossover, Gaussian mutation, elitism."""

    def __init__(self, population_size: int = 40, generations: int = 60, mutation_rate: float = 0.15, elite_fraction: float = 0.1):
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.elite_fraction = elite_fraction

    def optimise(self, objective_fn, bounds, seed=None, maximize=True, **kwargs) -> OptResult:
        rng = np.random.default_rng(seed)
        bounds = np.array(bounds, dtype=float)
        lo, hi = bounds[:, 0], bounds[:, 1]
        n_dim = len(bounds)
        n_elite = max(1, int(self.population_size * self.elite_fraction))

        pop = rng.uniform(lo, hi, size=(self.population_size, n_dim))
        history: list[float] = []
        n_eval = 0

        def fitness(x):
            v = objective_fn(x)
            return v if maximize else -v

        for _ in range(self.generations):
            scores = np.array([fitness(ind) for ind in pop])
            n_eval += len(pop)
            history.append(float(np.max(scores)))
            order = np.argsort(scores)[::-1]
            pop = pop[order]
            scores = scores[order]

            new_pop = [pop[i].copy() for i in range(n_elite)]
            while len(new_pop) < self.population_size:
                i, j = rng.choice(len(pop), size=2, replace=False)
                a, b = (pop[i], scores[i]) if scores[i] > scores[j] else (pop[j], scores[j])
                i2, j2 = rng.choice(len(pop), size=2, replace=False)
                c, _ = (pop[i2], scores[i2]) if scores[i2] > scores[j2] else (pop[j2], scores[j2])
                alpha = rng.uniform(0, 1, size=n_dim)
                child = alpha * a + (1 - alpha) * c
                mutate_mask = rng.uniform(size=n_dim) < self.mutation_rate
                child = np.where(mutate_mask, child + rng.normal(0, (hi - lo) * 0.1), child)
                child = np.clip(child, lo, hi)
                new_pop.append(child)
            pop = np.array(new_pop)

        scores = np.array([fitness(ind) for ind in pop])
        n_eval += len(pop)
        best_idx = np.argmax(scores)
        best_value = scores[best_idx] if maximize else -scores[best_idx]
        return OptResult(best_x=pop[best_idx], best_value=float(best_value), n_evaluations=n_eval, history=history, method="genetic_algorithm")


class BayesianOptimisationAlgorithm(OptimisationAlgorithm):
    """A minimal Gaussian-process Bayesian optimiser (RBF kernel, upper
    confidence bound acquisition), implemented directly on NumPy so it has
    no extra dependency. Suited to expensive, low-dimensional objective
    functions where the number of evaluations matters."""

    def __init__(self, n_initial: int = 8, n_iterations: int = 25, kappa: float = 2.0, length_scale: Optional[float] = None, noise: float = 1e-6):
        self.n_initial = n_initial
        self.n_iterations = n_iterations
        self.kappa = kappa
        self.length_scale = length_scale
        self.noise = noise

    @staticmethod
    def _rbf_kernel(x1, x2, length_scale):
        d2 = np.sum((x1[:, None, :] - x2[None, :, :]) ** 2, axis=-1)
        return np.exp(-d2 / (2 * length_scale**2))

    def _posterior(self, x_train, y_train, x_query, length_scale):
        k_train = self._rbf_kernel(x_train, x_train, length_scale) + self.noise * np.eye(len(x_train))
        k_query = self._rbf_kernel(x_query, x_train, length_scale)
        k_query_query = self._rbf_kernel(x_query, x_query, length_scale)

        chol = np.linalg.cholesky(k_train)
        alpha = np.linalg.solve(chol.T, np.linalg.solve(chol, y_train))
        mean = k_query @ alpha

        v = np.linalg.solve(chol, k_query.T)
        cov = k_query_query - v.T @ v
        var = np.clip(np.diag(cov), 1e-12, None)
        return mean, var

    def optimise(self, objective_fn, bounds, seed=None, maximize=True, **kwargs) -> OptResult:
        rng = np.random.default_rng(seed)
        bounds = np.array(bounds, dtype=float)
        lo, hi = bounds[:, 0], bounds[:, 1]
        n_dim = len(bounds)
        length_scale = self.length_scale or float(np.mean(hi - lo)) / 3.0 or 1.0

        x_train = rng.uniform(lo, hi, size=(self.n_initial, n_dim))
        signed_fn = _signed(objective_fn, maximize)
        y_train = np.array([signed_fn(x) for x in x_train])
        history = list(y_train if maximize else -y_train)

        for _ in range(self.n_iterations):
            candidates = rng.uniform(lo, hi, size=(200, n_dim))
            mean, var = self._posterior(x_train, y_train, candidates, length_scale)
            ucb = mean + self.kappa * np.sqrt(var)
            next_x = candidates[np.argmax(ucb)]
            next_y = signed_fn(next_x)
            x_train = np.vstack([x_train, next_x])
            y_train = np.append(y_train, next_y)
            history.append(next_y if maximize else -next_y)

        best_idx = np.argmax(y_train)
        best_value = y_train[best_idx] if maximize else -y_train[best_idx]
        return OptResult(best_x=x_train[best_idx], best_value=float(best_value), n_evaluations=len(y_train), history=history, method="bayesian_optimisation")


class LinearProgrammingAlgorithm:
    """Thin wrapper around ``scipy.optimize.linprog`` for genuinely linear
    problems (e.g. pumped-storage arbitrage scheduling) -- not a drop-in
    replacement for the nonlinear-objective ``optimise`` contract above,
    since LP requires an explicit linear cost vector and constraint
    matrices rather than an opaque objective function."""

    def solve(self, c, A_ub=None, b_ub=None, A_eq=None, b_eq=None, bounds=None, maximize: bool = True):
        cost = -np.asarray(c) if maximize else np.asarray(c)
        result = linprog(cost, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
        return result


class TorchGradientAlgorithm(OptimisationAlgorithm):
    """Gradient-descent optimisation via PyTorch autograd, for continuous,
    differentiable objectives where gradients materially speed up
    convergence over derivative-free search. Optional dependency: raises a
    clear ``ImportError`` only when actually used, never at import time."""

    def __init__(self, n_iterations: int = 200, lr: float = 0.05):
        self.n_iterations = n_iterations
        self.lr = lr

    def optimise(self, objective_fn, bounds, seed=None, maximize=True, **kwargs) -> OptResult:
        try:
            import torch
        except ImportError as exc:
            raise ImportError(
                "TorchGradientAlgorithm requires PyTorch. Install with `pip install hydroflux[torch]`."
            ) from exc

        if seed is not None:
            torch.manual_seed(seed)
        bounds_t = torch.tensor(bounds, dtype=torch.float64)
        lo, hi = bounds_t[:, 0], bounds_t[:, 1]
        x = torch.nn.Parameter((lo + hi) / 2)
        optimiser = torch.optim.Adam([x], lr=self.lr)
        history = []

        for _ in range(self.n_iterations):
            optimiser.zero_grad()
            clamped = torch.max(torch.min(x, hi), lo)
            value = objective_fn(clamped.detach().numpy())
            # Objective is treated as a black box w.r.t. autograd; approximate
            # the gradient by finite differences since HydroFlux objectives
            # are typically simulation-based, not natively differentiable.
            grad = np.zeros(len(bounds))
            eps = 1e-3 * (hi - lo).numpy()
            base = clamped.detach().numpy()
            for i in range(len(bounds)):
                perturbed = base.copy()
                perturbed[i] += eps[i]
                grad[i] = (objective_fn(perturbed) - value) / eps[i]
            x.grad = torch.tensor(-grad if maximize else grad, dtype=torch.float64)
            optimiser.step()
            history.append(value)

        best_x = torch.max(torch.min(x, hi), lo).detach().numpy()
        best_value = objective_fn(best_x)
        return OptResult(best_x=best_x, best_value=float(best_value), n_evaluations=self.n_iterations * (len(bounds) + 1), history=history, method="torch_gradient")


ALGORITHM_REGISTRY: dict[str, type] = {
    "scipy": ScipyMinimizeAlgorithm,
    "differential_evolution": DifferentialEvolutionAlgorithm,
    "monte_carlo": MonteCarloSearchAlgorithm,
    "genetic": GeneticAlgorithm,
    "bayesian": BayesianOptimisationAlgorithm,
    "torch": TorchGradientAlgorithm,
}


def get_algorithm(name: str, **kwargs) -> OptimisationAlgorithm:
    if name not in ALGORITHM_REGISTRY:
        raise ValueError(f"Unknown optimisation algorithm '{name}'. Available: {list(ALGORITHM_REGISTRY)}")
    return ALGORITHM_REGISTRY[name](**kwargs)
