"""Market-making agents of increasing sophistication (MM0, MM1, MM2)."""

from __future__ import annotations

class MarketMaker:
    """MM0: quote a fixed half-spread around the mid, ignoring everything else."""

    def __init__(self, half_spread: float, size: int, name: str = "MM0") -> None:
        self.half_spread = half_spread
        self.size = size
        self.name = name

    # Reservation price the quotes are centered on. MM0 uses the raw mid.
    def _reservation(self, mid: float, inventory: int) -> float:
        return mid

    # Effective half-spread. MM0 keeps it fixed.
    def _half_spread(self, flow_signal: float) -> float:
        return self.half_spread

    # Return (bid_price, bid_size, ask_price, ask_size) in integer ticks.
    def quote(self, mid: float, inventory: int, flow_signal: float) -> tuple[int, int, int, int]:
        r = self._reservation(mid, inventory)
        h = self._half_spread(flow_signal)
        return round(r - h), self.size, round(r + h), self.size


class MM1(MarketMaker):
    """Inventory-aware: shift the reservation price against inventory."""

    def __init__(
        self, 
        half_spread: float, 
        size: int, 
        gamma: float, 
        name: str = "MM1"
    ) -> None:
        super().__init__(half_spread, size, name)
        self.gamma = gamma

    def _reservation(self, mid: float, inventory: int) -> float:
        return mid - self.gamma * inventory


class MM2(MM1):
    """Adverse-selection-aware: MM1's skew plus a spread that widens with one-sided flow."""

    def __init__(
        self,
        half_spread: float,
        size: int,
        gamma: float,
        beta: float,
        name: str = "MM2",
    ) -> None:
        super().__init__(half_spread, size, gamma, name)
        self.beta = beta

    def _half_spread(self, flow_signal: float) -> float:
        return self.half_spread + self.beta * abs(flow_signal)