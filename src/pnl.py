"""PnL bookkeeping and the spread / inventory / adverse-selection decomposition."""

from __future__ import annotations

from dataclasses import dataclass, field

from orders import Side


@dataclass
class Fill:
    price: int          # Execution price in ticks.
    signed_size: int    # +size if the MM sold, -size if the MM bought.
    fair_value: float   # True fair value at the instant of the fill.
    informed: bool      # Whether the counterparty was an informed trader.


@dataclass
class PnLTracker:
    cash: float = 0.0
    inventory: int = 0
    fills: list[Fill] = field(default_factory=list)

    # Record one market-maker fill. mm_side is the side the MM traded on.
    def record(
        self, price: int, size: int, mm_side: Side, fair_value: float, informed: bool
    ) -> None:
        s = size if mm_side is Side.SELL else -size
        self.cash += price * s
        self.inventory -= s
        self.fills.append(Fill(price, s, fair_value, informed))

    # Total PnL marking leftover inventory to the final fair value.
    def total_pnl(self, final_value: float) -> float:
        return self.cash + self.inventory * final_value

    # Split total PnL two ways, both exact and additive to the total:
    #   1. spread capture vs inventory mark-to-market
    #   2. PnL earned on noise counterparties vs lost to informed counterparties
    def decompose(self, final_value: float) -> dict[str, float]:
        spread = sum(f.signed_size * (f.price - f.fair_value) for f in self.fills)
        inv_mtm = sum(
            f.signed_size * (f.fair_value - final_value) for f in self.fills
        )
        vs_informed = sum(
            f.signed_size * (f.price - final_value)
            for f in self.fills
            if f.informed
        )
        vs_noise = sum(
            f.signed_size * (f.price - final_value)
            for f in self.fills
            if not f.informed
        )
        return {
            "total": self.total_pnl(final_value),
            "spread_capture": spread,
            "inventory_mtm": inv_mtm,
            "pnl_vs_noise": vs_noise,
            "pnl_vs_informed": vs_informed,
        }
