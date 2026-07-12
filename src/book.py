"""The matching engine — a price-time-priority limit order book.

This is the *naive* version (DESIGN.md §3): correct first, fast later. The
price index is a plain sorted list (O(n) insert); Part A.5 swaps it for a heap
with lazy deletion and benchmarks the speedup. Everything here is written to be
obviously correct.

Design notes:
- Each side is a `dict[price -> deque[Order]]`. The deque gives FIFO time
  priority for free (append at the back, match from the front).
- Best prices come from a sorted list per side: best bid = last element,
  best ask = first element.
- `self._orders` maps id -> resting Order for O(1)-locate cancels.
- The caller supplies each order's id (a client order id); the exchange assigns
  the arrival `seq`.
- Trades always print at the *resting* order's price.
- A market order's unfilled remainder is discarded (immediate-or-cancel).
"""

from __future__ import annotations

import bisect
from collections import deque

from orders import Order, Side, Trade


class OrderBook:
    def __init__(self) -> None:
        # price -> queue of resting orders (FIFO = time priority)
        self._bids: dict[int, deque[Order]] = {}
        self._asks: dict[int, deque[Order]] = {}
        # sorted lists of active prices (ascending) for best-price lookup
        self._bid_prices: list[int] = []
        self._ask_prices: list[int] = []
        # id -> resting order, for O(1) cancel
        self._orders: dict[int, Order] = {}
        # monotonically increasing arrival/event counter
        self._seq: int = 0

    # ------------------------------------------------------------------ #
    # Best prices
    # ------------------------------------------------------------------ #
    def best_bid(self) -> int | None:
        """Highest price a buyer is currently willing to pay."""
        return self._bid_prices[-1] if self._bid_prices else None

    def best_ask(self) -> int | None:
        """Lowest price a seller is currently willing to accept."""
        return self._ask_prices[0] if self._ask_prices else None

    def mid(self) -> float | None:
        """Midpoint of the spread, or None if either side is empty."""
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return (bb + ba) / 2

    def spread(self) -> int | None:
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return ba - bb

    # ------------------------------------------------------------------ #
    # Submitting orders
    # ------------------------------------------------------------------ #
    def submit_limit(
        self, order_id: int, side: Side, price: int, quantity: int
    ) -> list[Trade]:
        """Submit a limit order. It matches against crossing resting orders;
        any remainder rests on the book. Returns the trades it produced."""
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if order_id in self._orders:
            raise ValueError(f"order id {order_id} is already resting")

        arrival = self._next_seq()
        trades, remaining = self._match(order_id, side, quantity, limit=price)

        if remaining > 0:
            order = Order(order_id, side, price, remaining, arrival)
            self._rest(order)
        return trades

    def submit_market(
        self, order_id: int, side: Side, quantity: int
    ) -> list[Trade]:
        """Submit a market order: match against the best available prices with
        no price limit. Any unfilled remainder is discarded (IOC)."""
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self._next_seq()  # a market order still occupies an arrival slot
        trades, _remaining = self._match(order_id, side, quantity, limit=None)
        return trades

    # ------------------------------------------------------------------ #
    # Cancelling
    # ------------------------------------------------------------------ #
    def cancel(self, order_id: int) -> bool:
        """Cancel a resting order by id. Raises KeyError if the id is unknown
        or already fully filled (see DESIGN.md §4 — matches test #7)."""
        if order_id not in self._orders:
            raise KeyError(order_id)
        order = self._orders.pop(order_id)
        book_side = self._bids if order.side is Side.BUY else self._asks
        prices = self._bid_prices if order.side is Side.BUY else self._ask_prices
        level = book_side.get(order.price)
        if level is not None:
            try:
                level.remove(order)
            except ValueError:
                pass
            if not level:
                del book_side[order.price]
                self._remove_price(prices, order.price)
        return True

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _match(
        self, incoming_id: int, side: Side, qty: int, limit: int | None
    ) -> tuple[list[Trade], int]:
        """Walk the opposite side, filling `qty` at resting prices best-first.

        `limit` is the incoming order's price, or None for a market order.
        Returns (trades, remaining_quantity).
        """
        trades: list[Trade] = []

        if side is Side.BUY:
            book_side, prices = self._asks, self._ask_prices
            best = lambda: prices[0]  # noqa: E731  (lowest ask is best)
            crosses = lambda p: limit is None or limit >= p  # noqa: E731
        else:
            book_side, prices = self._bids, self._bid_prices
            best = lambda: prices[-1]  # noqa: E731  (highest bid is best)
            crosses = lambda p: limit is None or limit <= p  # noqa: E731

        while qty > 0 and prices:
            level_price = best()
            if not crosses(level_price):
                break
            level = book_side[level_price]

            while qty > 0 and level:
                resting = level[0]
                fill = min(qty, resting.quantity)

                # Trade prints at the resting order's price.
                if side is Side.BUY:
                    buy_id, sell_id = incoming_id, resting.id
                else:
                    buy_id, sell_id = resting.id, incoming_id
                trades.append(
                    Trade(buy_id, sell_id, level_price, fill, self._next_seq())
                )

                resting.quantity -= fill
                qty -= fill
                if resting.quantity == 0:
                    level.popleft()
                    del self._orders[resting.id]

            if not level:
                del book_side[level_price]
                self._remove_price(prices, level_price)

        return trades, qty

    def _rest(self, order: Order) -> None:
        book_side = self._bids if order.side is Side.BUY else self._asks
        prices = self._bid_prices if order.side is Side.BUY else self._ask_prices
        if order.price not in book_side:
            book_side[order.price] = deque()
            bisect.insort(prices, order.price)  # O(n) — the naive cost
        book_side[order.price].append(order)
        self._orders[order.id] = order

    @staticmethod
    def _remove_price(prices: list[int], price: int) -> None:
        idx = bisect.bisect_left(prices, price)
        if idx < len(prices) and prices[idx] == price:
            prices.pop(idx)
