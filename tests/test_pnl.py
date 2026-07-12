"""Tests for the PnL decomposition, especially the exact additive identity."""

from pnl import PnLTracker
from orders import Side


def test_spread_plus_inventory_equals_total():
    t = PnLTracker()
    t.record(101, 10, Side.SELL, 100, informed=False)
    t.record(99, 10, Side.BUY, 100, informed=False)
    t.record(102, 5, Side.SELL, 101, informed=True)
    final = 103
    d = t.decompose(final)
    assert abs(d["spread_capture"] + d["inventory_mtm"] - d["total"]) < 1e-9


def test_sell_to_noise_flat_market_keeps_spread():
    t = PnLTracker()
    t.record(101, 10, Side.SELL, 100, informed=False)
    d = t.decompose(final_value=100)
    assert d["spread_capture"] == 10
    assert d["inventory_mtm"] == 0
    assert d["total"] == 10


def test_sell_to_shark_that_rises_loses():
    t = PnLTracker()
    t.record(101, 10, Side.SELL, 100, informed=True)
    d = t.decompose(final_value=105)
    assert d["spread_capture"] == 10
    assert d["inventory_mtm"] == -50
    assert d["total"] == -40
    assert d["pnl_vs_informed"] == -40  # full PnL on the informed trade


def test_counterparty_split_is_exact():
    t = PnLTracker()
    t.record(101, 10, Side.SELL, 100, informed=False)  # noise
    t.record(101, 10, Side.SELL, 100, informed=True)   # shark
    d = t.decompose(final_value=105)
    assert d["pnl_vs_informed"] == -40
    assert d["pnl_vs_noise"] == -40
    assert abs(d["pnl_vs_informed"] + d["pnl_vs_noise"] - d["total"]) < 1e-9


def test_buy_below_fair_is_positive_spread():
    t = PnLTracker()
    t.record(99, 10, Side.BUY, 100, informed=False)
    d = t.decompose(final_value=100)
    assert d["spread_capture"] == 10
    assert t.inventory == 10
