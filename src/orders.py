"""Domain objects for the order book — the shared vocabulary.

An `Order` is someone's intent to buy or sell; a `Trade` is the record of two
orders matching. These are plain data holders (see DESIGN.md §1); all logic
lives in the OrderBook.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Side(Enum):
    """Which side of the book an order is on."""

    BUY = 1
    SELL = 2

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY


@dataclass
class Order:
    """A resting or incoming order.

    Prices are integer ticks (never floats) so comparisons and dict-keying are
    exact. `quantity` is the *remaining* size and shrinks as the order fills.
    `seq` is a monotonically increasing arrival counter assigned by the
    exchange — it encodes time priority and, unlike a wall-clock timestamp, can
    never tie.
    """

    id: int
    side: Side
    price: int
    quantity: int
    seq: int


@dataclass
class Trade:
    """The record of one match: `quantity` shares changed hands at `price`.

    `price` is always the *resting* order's price (price-time priority — the
    order that was there first sets the terms). `seq` orders trades in time.
    """

    buy_id: int
    sell_id: int
    price: int
    quantity: int
    seq: int
