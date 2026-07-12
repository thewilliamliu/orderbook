"""Artificial order flow: noise traders and informed traders."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from orders import Side


@dataclass
class OrderIntent:
    side: Side          # Buy or sell.
    is_market: bool     # True for a market order, False for a limit order.
    price: int | None   # Limit price in ticks; None for a market order.
    size: int           # Quantity requested.


# A noise trader: random side, a market order with probability market_prob,
# otherwise a limit order jittered around the mid to add realistic depth.
def noise_order(
    mid: float,
    rng: np.random.Generator,
    market_prob: float,
    jitter_width: int,
    size: int,
) -> OrderIntent:
    side = Side.BUY if rng.random() < 0.5 else Side.SELL
    if rng.random() < market_prob:
        return OrderIntent(side, True, None, size)
    jitter = int(rng.integers(-jitter_width, jitter_width + 1))
    return OrderIntent(side, False, round(mid) + jitter, size)


# An informed trader: sees the future fair value and sends a market order in
# the profitable direction, or None when the edge is below the threshold.
def informed_order(
    mid: float, future_v: float, threshold: float, size: int
) -> OrderIntent | None:
    edge = future_v - mid
    if edge > threshold:
        return OrderIntent(Side.BUY, True, None, size)
    if edge < -threshold:
        return OrderIntent(Side.SELL, True, None, size)
    return None
