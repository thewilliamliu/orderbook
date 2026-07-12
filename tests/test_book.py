"""Tests for the matching engine.

The seven cases called out in the assignment (A.4) are marked [required].
Everything else pushes coverage past 20 and pins down edge cases. Written to
be read: each test asserts one behavior.
"""

import pytest

from book import OrderBook
from orders import Side


# --------------------------------------------------------------------------- #
# Empty book / best prices
# --------------------------------------------------------------------------- #
def test_empty_book_has_no_best_prices():
    b = OrderBook()
    assert b.best_bid() is None
    assert b.best_ask() is None
    assert b.mid() is None
    assert b.spread() is None


def test_single_resting_bid_sets_best_bid_only():
    b = OrderBook()
    trades = b.submit_limit(1, Side.BUY, 100, 10)
    assert trades == []
    assert b.best_bid() == 100
    assert b.best_ask() is None
    assert b.mid() is None  # only one side


def test_mid_and_spread_with_both_sides():
    b = OrderBook()
    b.submit_limit(1, Side.BUY, 99, 10)
    b.submit_limit(2, Side.SELL, 101, 10)
    assert b.best_bid() == 99
    assert b.best_ask() == 101
    assert b.mid() == 100.0
    assert b.spread() == 2


# --------------------------------------------------------------------------- #
# [required 1] resting when it doesn't cross
# --------------------------------------------------------------------------- #
def test_noncrossing_limit_rests_and_updates_best():
    b = OrderBook()
    b.submit_limit(1, Side.BUY, 100, 10)
    # A sell at 101 doesn't cross the bid of 100 -> rests, no trade.
    trades = b.submit_limit(2, Side.SELL, 101, 5)
    assert trades == []
    assert b.best_bid() == 100
    assert b.best_ask() == 101


def test_best_bid_tracks_highest_of_several():
    b = OrderBook()
    b.submit_limit(1, Side.BUY, 98, 10)
    b.submit_limit(2, Side.BUY, 100, 10)
    b.submit_limit(3, Side.BUY, 99, 10)
    assert b.best_bid() == 100
    b.submit_limit(4, Side.BUY, 101, 10)
    assert b.best_bid() == 101


# --------------------------------------------------------------------------- #
# [required 2] crossing fills at the RESTING price (price improvement)
# --------------------------------------------------------------------------- #
def test_cross_fills_at_resting_price_buy_improves():
    b = OrderBook()
    b.submit_limit(1, Side.SELL, 100, 10)  # resting ask at 100
    # Buyer willing to pay up to 105 — but should fill at the resting 100.
    trades = b.submit_limit(2, Side.BUY, 105, 10)
    assert len(trades) == 1
    assert trades[0].price == 100  # price improvement, not 105
    assert trades[0].buy_id == 2
    assert trades[0].sell_id == 1
    assert trades[0].quantity == 10
    assert b.best_ask() is None  # ask fully consumed


def test_cross_fills_at_resting_price_sell_improves():
    b = OrderBook()
    b.submit_limit(1, Side.BUY, 100, 10)  # resting bid at 100
    # Seller willing to accept as low as 95 — fills at the resting 100.
    trades = b.submit_limit(2, Side.SELL, 95, 10)
    assert len(trades) == 1
    assert trades[0].price == 100
    assert trades[0].buy_id == 1
    assert trades[0].sell_id == 2


# --------------------------------------------------------------------------- #
# [required 3] partial fill
# --------------------------------------------------------------------------- #
def test_partial_fill_incoming_larger_leaves_remainder_resting():
    b = OrderBook()
    b.submit_limit(1, Side.SELL, 100, 60)
    trades = b.submit_limit(2, Side.BUY, 100, 100)
    assert len(trades) == 1
    assert trades[0].quantity == 60
    # 40 remainder rests on the bid side at 100.
    assert b.best_bid() == 100
    assert b.best_ask() is None


def test_partial_fill_resting_larger_keeps_resting():
    b = OrderBook()
    b.submit_limit(1, Side.SELL, 100, 100)
    trades = b.submit_limit(2, Side.BUY, 100, 60)
    assert trades[0].quantity == 60
    # 40 of the resting ask remains.
    assert b.best_ask() == 100
    assert b.best_bid() is None


# --------------------------------------------------------------------------- #
# [required 4] time priority within a price level
# --------------------------------------------------------------------------- #
def test_time_priority_fifo_at_same_price():
    b = OrderBook()
    b.submit_limit(1, Side.SELL, 100, 10)  # arrives first
    b.submit_limit(2, Side.SELL, 100, 10)  # arrives second
    trades = b.submit_limit(3, Side.BUY, 100, 10)
    assert len(trades) == 1
    assert trades[0].sell_id == 1  # oldest filled first
    # Second order still resting.
    trades2 = b.submit_limit(4, Side.BUY, 100, 10)
    assert trades2[0].sell_id == 2


def test_time_priority_market_order_across_queue():
    b = OrderBook()
    b.submit_limit(1, Side.SELL, 100, 10)
    b.submit_limit(2, Side.SELL, 100, 10)
    b.submit_limit(3, Side.SELL, 100, 10)
    trades = b.submit_market(9, Side.BUY, 25)
    assert [t.sell_id for t in trades] == [1, 2, 3]
    assert [t.quantity for t in trades] == [10, 10, 5]
    assert b.best_ask() == 100  # 5 of order 3 remains


# --------------------------------------------------------------------------- #
# [required 5] cancel of a partially filled order removes only the remainder
# --------------------------------------------------------------------------- #
def test_cancel_partially_filled_removes_remainder():
    b = OrderBook()
    b.submit_limit(1, Side.SELL, 100, 100)
    b.submit_limit(2, Side.BUY, 100, 60)  # fills 60, 40 of order 1 rests
    assert b.best_ask() == 100
    assert b.cancel(1) is True
    assert b.best_ask() is None  # remainder gone


# --------------------------------------------------------------------------- #
# [required 6] market order walks multiple levels -> multiple trades
# --------------------------------------------------------------------------- #
def test_market_order_walks_multiple_levels():
    b = OrderBook()
    b.submit_limit(1, Side.SELL, 100, 10)
    b.submit_limit(2, Side.SELL, 101, 10)
    b.submit_limit(3, Side.SELL, 102, 10)
    trades = b.submit_market(9, Side.BUY, 25)
    assert [t.price for t in trades] == [100, 101, 102]
    assert [t.quantity for t in trades] == [10, 10, 5]
    assert b.best_ask() == 102  # 5 left at 102


def test_limit_order_walks_multiple_levels_then_rests():
    b = OrderBook()
    b.submit_limit(1, Side.SELL, 100, 10)
    b.submit_limit(2, Side.SELL, 101, 10)
    # Buy 30 @ up-to-101: takes 100 and 101 (20), remainder 10 rests at 101.
    trades = b.submit_limit(3, Side.BUY, 101, 30)
    assert [t.price for t in trades] == [100, 101]
    assert sum(t.quantity for t in trades) == 20
    assert b.best_bid() == 101  # 10 rests as a bid
    assert b.best_ask() is None


# --------------------------------------------------------------------------- #
# [required 7] cancel of unknown / already-filled id raises cleanly
# --------------------------------------------------------------------------- #
def test_cancel_unknown_id_raises():
    b = OrderBook()
    with pytest.raises(KeyError):
        b.cancel(999)


def test_cancel_already_filled_id_raises():
    b = OrderBook()
    b.submit_limit(1, Side.SELL, 100, 10)
    b.submit_limit(2, Side.BUY, 100, 10)  # fully fills order 1
    with pytest.raises(KeyError):
        b.cancel(1)


def test_cancel_twice_raises_second_time():
    b = OrderBook()
    b.submit_limit(1, Side.BUY, 100, 10)
    assert b.cancel(1) is True
    with pytest.raises(KeyError):
        b.cancel(1)


# --------------------------------------------------------------------------- #
# Level lifecycle / removal
# --------------------------------------------------------------------------- #
def test_exact_fill_removes_level():
    b = OrderBook()
    b.submit_limit(1, Side.SELL, 100, 10)
    b.submit_limit(2, Side.BUY, 100, 10)
    assert b.best_ask() is None
    assert b.best_bid() is None  # nothing left resting


def test_cancel_only_order_removes_price_level():
    b = OrderBook()
    b.submit_limit(1, Side.BUY, 100, 10)
    b.submit_limit(2, Side.BUY, 99, 10)
    b.cancel(1)
    assert b.best_bid() == 99  # 100 level gone


def test_cancel_middle_order_preserves_fifo():
    b = OrderBook()
    b.submit_limit(1, Side.SELL, 100, 10)
    b.submit_limit(2, Side.SELL, 100, 10)
    b.submit_limit(3, Side.SELL, 100, 10)
    b.cancel(2)  # remove the middle of the queue
    trades = b.submit_market(9, Side.BUY, 20)
    assert [t.sell_id for t in trades] == [1, 3]  # 2 skipped, order preserved


# --------------------------------------------------------------------------- #
# Market order edge cases
# --------------------------------------------------------------------------- #
def test_market_order_on_empty_book_no_trades():
    b = OrderBook()
    trades = b.submit_market(9, Side.BUY, 10)
    assert trades == []
    assert b.best_bid() is None and b.best_ask() is None


def test_market_order_remainder_is_discarded():
    b = OrderBook()
    b.submit_limit(1, Side.SELL, 100, 10)
    trades = b.submit_market(9, Side.BUY, 25)  # only 10 available
    assert sum(t.quantity for t in trades) == 10
    # The unfilled 15 is discarded, not rested.
    assert b.best_bid() is None
    assert b.best_ask() is None


def test_large_market_consumes_entire_side():
    b = OrderBook()
    b.submit_limit(1, Side.BUY, 100, 10)
    b.submit_limit(2, Side.BUY, 99, 10)
    trades = b.submit_market(9, Side.SELL, 100)
    assert sum(t.quantity for t in trades) == 20
    assert b.best_bid() is None


# --------------------------------------------------------------------------- #
# Non-crossing limits that sit on both sides; trade orientation
# --------------------------------------------------------------------------- #
def test_limit_below_market_rests_without_crossing():
    b = OrderBook()
    b.submit_limit(1, Side.SELL, 105, 10)
    b.submit_limit(2, Side.BUY, 100, 10)  # below the ask -> rests
    assert b.best_bid() == 100
    assert b.best_ask() == 105
    assert b.spread() == 5


def test_trade_ids_orientation_on_sell_aggressor():
    b = OrderBook()
    b.submit_limit(1, Side.BUY, 100, 10)  # resting buyer
    trades = b.submit_limit(2, Side.SELL, 100, 10)  # aggressive seller
    assert trades[0].buy_id == 1
    assert trades[0].sell_id == 2
    assert trades[0].price == 100


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def test_zero_quantity_rejected():
    b = OrderBook()
    with pytest.raises(ValueError):
        b.submit_limit(1, Side.BUY, 100, 0)


def test_duplicate_resting_id_rejected():
    b = OrderBook()
    b.submit_limit(1, Side.BUY, 100, 10)
    with pytest.raises(ValueError):
        b.submit_limit(1, Side.BUY, 99, 10)  # id 1 already resting


def test_reusing_id_after_full_fill_is_allowed():
    b = OrderBook()
    b.submit_limit(1, Side.SELL, 100, 10)
    b.submit_limit(2, Side.BUY, 100, 10)  # order 1 fully filled and freed
    # id 1 is free again — reuse should not raise.
    b.submit_limit(1, Side.BUY, 99, 10)
    assert b.best_bid() == 99
