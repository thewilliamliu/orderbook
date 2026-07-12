"""Tests for the simulation harness: determinism and basic sanity."""

import numpy as np

from config import SimConfig
from market_maker import MarketMaker
from simulator import Simulator


def _run(seed=0, n_ticks=500):
    cfg = SimConfig(n_ticks=n_ticks, seed=seed)
    mm = MarketMaker(cfg.mm_half_spread, cfg.mm_size)
    return Simulator().run(mm, cfg, np.random.default_rng(cfg.seed))


def test_same_seed_reproduces_run():
    a = _run(seed=42)
    b = _run(seed=42)
    assert np.array_equal(a.pnl, b.pnl)
    assert a.final_pnl == b.final_pnl


def test_different_seed_changes_run():
    a = _run(seed=1)
    b = _run(seed=2)
    assert not np.array_equal(a.pnl, b.pnl)


def test_result_arrays_have_expected_length():
    r = _run(n_ticks=300)
    assert len(r.pnl) == 300
    assert len(r.inventory) == 300
    assert len(r.fair_value) == 300


def test_decomposition_identity_holds_in_sim():
    r = _run(seed=7)
    d = r.decomposition
    assert abs(d["spread_capture"] + d["inventory_mtm"] - d["total"]) < 1e-6


def test_no_informed_flow_means_nothing_lost_to_informed():
    cfg = SimConfig(n_ticks=500, p=0.0, seed=3)
    mm = MarketMaker(cfg.mm_half_spread, cfg.mm_size)
    r = Simulator().run(mm, cfg, np.random.default_rng(cfg.seed))
    assert r.decomposition["pnl_vs_informed"] == 0
