"""The latent fair value process (a random walk to get V)."""

from __future__ import annotations

import numpy as np

# One random-walk step: V(t+1) = V(t) + sigma * epsilon, epsilon ~ Normal(0, 1).
def random_walk_step(v: float, sigma: float, rng: np.random.Generator) -> float:
    return v + sigma * rng.standard_normal()

# Pre-generate the full fair-value path so informed traders can look k ticks
# ahead. Returns an array of length n_steps + 1 starting at v0.
def random_walk_path(v0: float, sigma: float, n_steps: int, rng: np.random.Generator) -> np.ndarray:
    increments = sigma * rng.standard_normal(n_steps)
    return np.concatenate([[v0], v0 + np.cumsum(increments)])
