"""Limit order book with price-time priority matching."""

from __future__ import annotations
import heapq
from collections import deque
from orders import Order, Side, Trade

class OrderBook:
    def __init__(self) -> None:
        # At each price level, return a FIFO queue of resting orders (time priority).
        self._bids: dict[int, deque[Order]] = {}
        self._asks: dict[int, deque[Order]] = {}
        # Price indices. Bids store negated prices so the min-heap yields the
        # highest bid on top; asks store prices directly for the lowest ask.
        self._bid_heap: list[int] = []
        self._ask_heap: list[int] = []
        # Order ID -> resting order, for O(1) cancels.
        self._orders: dict[int, Order] = {}
        # Monotonically increasing counters for order IDs and event timestamps.
        self._next_id = 1
        self._clock = 0

    # Highest price a buyer is currently willing to pay.
    def best_bid(self) -> int | None:
        self._prune(self._bid_heap, self._bids, negated=True) # Lazy deletion.
        return -self._bid_heap[0] if self._bid_heap else None

    # Lowest price a seller is currently willing to accept.
    def best_ask(self) -> int | None:
        self._prune(self._ask_heap, self._asks, negated=False) # Lazy deletion.
        return self._ask_heap[0] if self._ask_heap else None

    # Midpoint between the best bid and ask, or None if either side is empty.
    def mid(self) -> float | None:
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return (bb + ba) / 2

    # Gap between the best ask and best bid.
    def spread(self) -> int | None:
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return ba - bb

    # Submit a limit order. Returns (assigned_id, trades); any unfilled remainder rests on the book under assigned_id.
    def submit_limit(self, side: Side, price: int, quantity: int) -> tuple[int, list[Trade]]:
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        order_id = self._assign_id()
        arrival = self._tick()

        trades, remaining = self._match(order_id, side, quantity, limit=price)
        if remaining > 0:
            self._rest(Order(order_id, side, price, remaining, arrival))
        return order_id, trades

    # Submit a market order. Returns (assigned_id, trades); any unfilled remainder is discarded (immediate-or-cancel).
    def submit_market(self, side: Side, quantity: int) -> tuple[int, list[Trade]]:
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        order_id = self._assign_id()
        self._tick()
        
        trades, _ = self._match(order_id, side, quantity, limit=None)
        return order_id, trades

    # Cancel a resting order by ID. Returns True if an order was removed,
    # False if the ID is unknown or already filled.
    def cancel(self, order_id: int) -> bool:
        order = self._orders.pop(order_id, None)
        if order is None:
            return False
        
        levels = self._bids if order.side is Side.BUY else self._asks

        level = levels.get(order.price)
        if level is not None:
            try:
                level.remove(order)
            except ValueError:
                pass
            if not level:
                del levels[order.price]
        return True

    # Assign the next unique order ID.
    def _assign_id(self) -> int:
        oid = self._next_id
        self._next_id += 1
        return oid

    # Advance and return the monotonic event clock.
    def _tick(self) -> int:
        self._clock += 1
        return self._clock

    # Matching engine.
    def _match(self, incoming_id: int, side: Side, qty: int, limit: int | None) -> tuple[list[Trade], int]:
        trades: list[Trade] = []
        
        # Determine the side of the book to match against, create correct crossing function.
        if side is Side.BUY:
            levels, best = self._asks, self.best_ask
            crosses = lambda p: limit is None or limit >= p  # noqa: E731
        else:
            levels, best = self._bids, self.best_bid
            crosses = lambda p: limit is None or limit <= p  # noqa: E731

        # Walk the opposite side price levels, filling qty best-price-first at resting prices.
        while qty > 0:
            level_price = best()
            if level_price is None or not crosses(level_price):
                break
            queue = levels[level_price] # FIFO queue of resting orders at this price level.

            # Walk the FIFO queue of resting orders at this price level.
            while qty > 0 and queue:
                resting = queue[0] 
                fill = min(qty, resting.quantity)

                if side is Side.BUY:
                    buy_id, sell_id = incoming_id, resting.id
                else:
                    buy_id, sell_id = resting.id, incoming_id

                trades.append(
                    Trade(buy_id, sell_id, level_price, fill, self._tick())
                )

                resting.quantity -= fill
                qty -= fill

                if resting.quantity == 0:
                    queue.popleft()
                    del self._orders[resting.id]

            if not queue:
                del levels[level_price]  # Heap entry pruned lazily on read.
            
        return trades, qty

    # Rest an order on its own side, creating the price level if needed.
    def _rest(self, order: Order) -> None:
        if order.side is Side.BUY:
            levels, heap, key = self._bids, self._bid_heap, -order.price
        else:
            levels, heap, key = self._asks, self._ask_heap, order.price
        
        if order.price not in levels:
            levels[order.price] = deque()
            heapq.heappush(heap, key) # Pushes heap-signed price.
        levels[order.price].append(order)
        self._orders[order.id] = order

    # Discard heap entries whose price levels no longer exist (lazy deletion).
    @staticmethod
    def _prune(heap: list[int], levels: dict[int, deque], negated: bool) -> None:
        while heap:
            price = -heap[0] if negated else heap[0]
            if price in levels:
                return
            heapq.heappop(heap)
