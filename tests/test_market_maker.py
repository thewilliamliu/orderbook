"""Tests for the three market-making agents."""

from market_maker import MarketMaker, MM1, MM2


def test_mm0_quotes_symmetric_around_mid():
    mm = MarketMaker(half_spread=3, size=2)
    bid_px, bid_sz, ask_px, ask_sz = mm.quote(mid=100, inventory=0, flow_signal=0)
    assert bid_px == 97
    assert ask_px == 103
    assert bid_sz == ask_sz == 2


def test_mm0_ignores_inventory_and_flow():
    mm = MarketMaker(half_spread=3, size=2)
    a = mm.quote(mid=100, inventory=50, flow_signal=100)
    b = mm.quote(mid=100, inventory=0, flow_signal=0)
    assert a == b


def test_mm1_long_inventory_shifts_quotes_down():
    mm = MM1(half_spread=3, size=2, gamma=0.2)
    flat = mm.quote(mid=100, inventory=0, flow_signal=0)
    long = mm.quote(mid=100, inventory=40, flow_signal=0)
    assert long[0] < flat[0]   # bid drops
    assert long[2] < flat[2]   # ask drops


def test_mm1_short_inventory_shifts_quotes_up():
    mm = MM1(half_spread=3, size=2, gamma=0.2)
    flat = mm.quote(mid=100, inventory=0, flow_signal=0)
    short = mm.quote(mid=100, inventory=-40, flow_signal=0)
    assert short[0] > flat[0]
    assert short[2] > flat[2]


def test_mm2_widens_spread_on_one_sided_flow():
    mm = MM2(half_spread=3, size=2, gamma=0.2, beta=0.1)
    calm = mm.quote(mid=100, inventory=0, flow_signal=0)
    toxic = mm.quote(mid=100, inventory=0, flow_signal=50)
    calm_spread = calm[2] - calm[0]
    toxic_spread = toxic[2] - toxic[0]
    assert toxic_spread > calm_spread
