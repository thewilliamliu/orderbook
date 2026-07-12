"""Tests for the matching engine. The seven assignment cases are marked."""

from book import OrderBook
from orders import Side


def test_empty_book_has_no_best_prices():
    b = OrderBook()
    assert b.best_bid() is None
    assert b.best_ask() is None
    assert b.mid() is None
    assert b.spread() is None


def test_single_resting_bid_sets_best_bid_only():
    b = OrderBook()
    _, trades = b.submit_limit(Side.BUY, 100, 10)
    assert trades == []
    assert b.best_bid() == 100
    assert b.best_ask() is None
    assert b.mid() is None


def test_mid_and_spread_with_both_sides():
    b = OrderBook()
    b.submit_limit(Side.BUY, 99, 10)
    b.submit_limit(Side.SELL, 101, 10)
    assert b.best_bid() == 99
    assert b.best_ask() == 101
    assert b.mid() == 100.0
    assert b.spread() == 2


# Assignment case 1: a non-crossing limit rests and updates the best prices.
def test_noncrossing_limit_rests():
    b = OrderBook()
    b.submit_limit(Side.BUY, 100, 10)
    _, trades = b.submit_limit(Side.SELL, 101, 5)
    assert trades == []
    assert b.best_bid() == 100
    assert b.best_ask() == 101


def test_best_bid_tracks_highest_of_several():
    b = OrderBook()
    b.submit_limit(Side.BUY, 98, 10)
    b.submit_limit(Side.BUY, 100, 10)
    b.submit_limit(Side.BUY, 99, 10)
    assert b.best_bid() == 100
    b.submit_limit(Side.BUY, 101, 10)
    assert b.best_bid() == 101


def test_best_ask_tracks_lowest_of_several():
    b = OrderBook()
    b.submit_limit(Side.SELL, 103, 10)
    b.submit_limit(Side.SELL, 101, 10)
    b.submit_limit(Side.SELL, 102, 10)
    assert b.best_ask() == 101


# Assignment case 2: a crossing order fills at the resting price (improvement).
def test_cross_fills_at_resting_price_buy_improves():
    b = OrderBook()
    sid, _ = b.submit_limit(Side.SELL, 100, 10)
    bid, trades = b.submit_limit(Side.BUY, 105, 10)
    assert len(trades) == 1
    assert trades[0].price == 100
    assert trades[0].buy_id == bid
    assert trades[0].sell_id == sid
    assert b.best_ask() is None


def test_cross_fills_at_resting_price_sell_improves():
    b = OrderBook()
    bid, _ = b.submit_limit(Side.BUY, 100, 10)
    sid, trades = b.submit_limit(Side.SELL, 95, 10)
    assert trades[0].price == 100
    assert trades[0].buy_id == bid
    assert trades[0].sell_id == sid


# Assignment case 3: a partial fill leaves the remainder resting.
def test_partial_fill_incoming_larger_leaves_remainder():
    b = OrderBook()
    b.submit_limit(Side.SELL, 100, 60)
    _, trades = b.submit_limit(Side.BUY, 100, 100)
    assert len(trades) == 1
    assert trades[0].quantity == 60
    assert b.best_bid() == 100
    assert b.best_ask() is None


def test_partial_fill_resting_larger_keeps_resting():
    b = OrderBook()
    b.submit_limit(Side.SELL, 100, 100)
    _, trades = b.submit_limit(Side.BUY, 100, 60)
    assert trades[0].quantity == 60
    assert b.best_ask() == 100
    assert b.best_bid() is None


# Assignment case 4: time priority within a price level is FIFO.
def test_time_priority_fifo_at_same_price():
    b = OrderBook()
    first, _ = b.submit_limit(Side.SELL, 100, 10)
    second, _ = b.submit_limit(Side.SELL, 100, 10)
    _, trades = b.submit_limit(Side.BUY, 100, 10)
    assert trades[0].sell_id == first
    _, trades2 = b.submit_limit(Side.BUY, 100, 10)
    assert trades2[0].sell_id == second


# Assignment case 6: a market order walks multiple levels, one trade each.
def test_market_order_walks_multiple_levels():
    b = OrderBook()
    b.submit_limit(Side.SELL, 100, 10)
    b.submit_limit(Side.SELL, 101, 10)
    b.submit_limit(Side.SELL, 102, 10)
    _, trades = b.submit_market(Side.BUY, 25)
    assert [t.price for t in trades] == [100, 101, 102]
    assert [t.quantity for t in trades] == [10, 10, 5]
    assert b.best_ask() == 102


def test_limit_order_walks_multiple_levels_then_rests():
    b = OrderBook()
    b.submit_limit(Side.SELL, 100, 10)
    b.submit_limit(Side.SELL, 101, 10)
    _, trades = b.submit_limit(Side.BUY, 101, 30)
    assert [t.price for t in trades] == [100, 101]
    assert sum(t.quantity for t in trades) == 20
    assert b.best_bid() == 101
    assert b.best_ask() is None


# Assignment case 5: cancelling a partially filled order drops only the rest.
def test_cancel_partially_filled_removes_remainder():
    b = OrderBook()
    sid, _ = b.submit_limit(Side.SELL, 100, 100)
    b.submit_limit(Side.BUY, 100, 60)
    assert b.best_ask() == 100
    assert b.cancel(sid) is True
    assert b.best_ask() is None


# Assignment case 7: cancelling an unknown or filled id is handled cleanly.
def test_cancel_unknown_id_returns_false():
    b = OrderBook()
    assert b.cancel(999) is False


def test_cancel_already_filled_id_returns_false():
    b = OrderBook()
    sid, _ = b.submit_limit(Side.SELL, 100, 10)
    b.submit_limit(Side.BUY, 100, 10)
    assert b.cancel(sid) is False


def test_cancel_twice_returns_false_second_time():
    b = OrderBook()
    oid, _ = b.submit_limit(Side.BUY, 100, 10)
    assert b.cancel(oid) is True
    assert b.cancel(oid) is False


def test_exact_fill_empties_book():
    b = OrderBook()
    b.submit_limit(Side.SELL, 100, 10)
    b.submit_limit(Side.BUY, 100, 10)
    assert b.best_ask() is None
    assert b.best_bid() is None


def test_cancel_only_order_prunes_price_level():
    b = OrderBook()
    top, _ = b.submit_limit(Side.BUY, 100, 10)
    b.submit_limit(Side.BUY, 99, 10)
    b.cancel(top)
    assert b.best_bid() == 99


def test_cancel_middle_order_preserves_fifo():
    b = OrderBook()
    first, _ = b.submit_limit(Side.SELL, 100, 10)
    middle, _ = b.submit_limit(Side.SELL, 100, 10)
    last, _ = b.submit_limit(Side.SELL, 100, 10)
    b.cancel(middle)
    _, trades = b.submit_market(Side.BUY, 20)
    assert [t.sell_id for t in trades] == [first, last]


def test_market_order_on_empty_book_no_trades():
    b = OrderBook()
    _, trades = b.submit_market(Side.BUY, 10)
    assert trades == []
    assert b.best_bid() is None and b.best_ask() is None


def test_market_order_remainder_is_discarded():
    b = OrderBook()
    b.submit_limit(Side.SELL, 100, 10)
    _, trades = b.submit_market(Side.BUY, 25)
    assert sum(t.quantity for t in trades) == 10
    assert b.best_bid() is None
    assert b.best_ask() is None


def test_large_market_consumes_entire_side():
    b = OrderBook()
    b.submit_limit(Side.BUY, 100, 10)
    b.submit_limit(Side.BUY, 99, 10)
    _, trades = b.submit_market(Side.SELL, 100)
    assert sum(t.quantity for t in trades) == 20
    assert b.best_bid() is None


def test_recreated_price_level_still_best():
    b = OrderBook()
    a, _ = b.submit_limit(Side.SELL, 100, 10)
    b.submit_market(Side.BUY, 10)          # Empties the 100 level.
    b.submit_limit(Side.SELL, 100, 5)      # Recreate it (stale heap entry).
    assert b.best_ask() == 100             # Pruning must skip the stale entry.


def test_trade_ids_orientation_on_sell_aggressor():
    b = OrderBook()
    bid, _ = b.submit_limit(Side.BUY, 100, 10)
    sid, trades = b.submit_limit(Side.SELL, 100, 10)
    assert trades[0].buy_id == bid
    assert trades[0].sell_id == sid
    assert trades[0].price == 100


def test_zero_quantity_rejected():
    b = OrderBook()
    try:
        b.submit_limit(Side.BUY, 100, 0)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_ids_are_unique_and_increasing():
    b = OrderBook()
    a, _ = b.submit_limit(Side.BUY, 100, 10)
    c, _ = b.submit_limit(Side.SELL, 101, 10)
    assert c > a
