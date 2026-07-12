"""Domain objects shared across the project. Side, Order, Trade."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

class Side(Enum):
    BUY = 0
    SELL = 1

    @property
    def opposite(self) -> "Side":
        # The other side of the book.
        return Side.SELL if self is Side.BUY else Side.BUY


@dataclass
class Order:
    id: int          # Unique ID assigned by the exchange.
    side: Side       # Buy or sell.
    price: int       # Integer ticks; ignored for market orders.
    quantity: int    # Remaining quantity, decremented as the order fills.
    timestamp: int   # Monotonically increasing arrival counter (time priority).


@dataclass
class Trade:
    buy_id: int      # ID of the order on the buy side.
    sell_id: int     # ID of the order on the sell side.
    price: int       # The resting order's price (price-time priority).
    quantity: int    # Shares exchanged.
    timestamp: int   # Monotonically increasing event counter.
