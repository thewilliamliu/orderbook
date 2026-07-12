"""Configuration for a simulation run."""

from __future__ import annotations

from dataclasses import dataclass

@dataclass
class SimConfig:
    n_ticks: int = 4000          # Number of ticks to simulate.
    initial_price: int = 10000   # Starting fair value in ticks.
    sigma: float = 3.0           # Fair-value volatility per tick.

    lam: float = 6.0             # Mean noise orders per tick (Poisson rate).
    noise_market_prob: float = 0.5  # Chance a noise order is a market order.
    jitter_width: int = 6        # Half-width of noise limit-price jitter.
    noise_size: int = 1          # Noise order size.

    p: float = 0.1               # Chance an informed trader arrives per tick.
    k: int = 5                   # How many ticks ahead the informed trader sees.
    threshold: float = 2.0       # Minimum edge before an informed trader acts.
    informed_size: int = 3       # Informed order size.

    mm_half_spread: float = 3.0  # Market-maker base half-spread.
    mm_size: int = 2             # Market-maker quote size.
    mm_gamma: float = 0.15       # Inventory-aversion coefficient (MM1, MM2).
    mm_beta: float = 0.05        # Toxicity sensitivity (MM2).
    flow_window: int = 25        # Trades kept for the signed-flow signal.

    seed: int = 0                # RNG seed for reproducibility.
