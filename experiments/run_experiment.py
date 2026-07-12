"""Run the three market makers, decompose their PnL, and save the figures.

Usage: python experiments/run_experiment.py
Outputs (written next to this file):
    pnl_over_time.png       PnL of MM0/MM1/MM2 at a fixed informed probability
    final_pnl_vs_p.png      Final PnL vs informed probability (the money chart)
    inventory_over_time.png Inventory of MM0 vs MM1
    summary.csv             PnL decomposition table across p
"""

from __future__ import annotations

import csv
import os
import sys

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import SimConfig  # noqa: E402
from market_maker import MarketMaker, MM1, MM2  # noqa: E402
from simulator import Simulator  # noqa: E402

HERE = os.path.dirname(__file__)
P_VALUES = [0.0, 0.05, 0.1, 0.2]
SEEDS = list(range(10))
FIXED_P = 0.1
COLORS = {"MM0": "#c0392b", "MM1": "#2980b9", "MM2": "#27ae60"}


# Build a market maker of the given name from the config parameters.
def build(cfg: SimConfig, name: str) -> MarketMaker:
    if name == "MM0":
        return MarketMaker(cfg.mm_half_spread, cfg.mm_size, "MM0")
    if name == "MM1":
        return MM1(cfg.mm_half_spread, cfg.mm_size, cfg.mm_gamma, "MM1")
    return MM2(cfg.mm_half_spread, cfg.mm_size, cfg.mm_gamma, cfg.mm_beta, "MM2")


# Run one simulation for a given market maker, informed probability, and seed.
def run_one(name: str, p: float, seed: int):
    cfg = SimConfig(p=p, seed=seed)
    return Simulator().run(build(cfg, name), cfg, np.random.default_rng(seed))


# Figure 1: PnL over time for all three MMs at a fixed informed probability.
def figure_pnl_over_time() -> None:
    plt.figure(figsize=(9, 5))
    for name in ("MM0", "MM1", "MM2"):
        r = run_one(name, FIXED_P, seed=0)
        plt.plot(r.ticks, r.pnl, label=name, color=COLORS[name])
    plt.axhline(0, color="gray", lw=0.8, ls="--")
    plt.title(f"PnL over time (informed probability p = {FIXED_P})")
    plt.xlabel("tick")
    plt.ylabel("PnL (ticks)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(HERE, "pnl_over_time.png"), dpi=130)
    plt.close()


# Figure 2: final PnL vs informed probability, averaged over seeds.
def figure_final_pnl_vs_p() -> dict:
    means = {name: [] for name in ("MM0", "MM1", "MM2")}
    for name in means:
        for p in P_VALUES:
            vals = [run_one(name, p, s).final_pnl for s in SEEDS]
            means[name].append(np.mean(vals))
    plt.figure(figsize=(9, 5))
    for name in means:
        plt.plot(P_VALUES, means[name], marker="o", label=name, color=COLORS[name])
    plt.axhline(0, color="gray", lw=0.8, ls="--")
    plt.title("Final PnL vs informed-trader probability")
    plt.xlabel("informed probability p")
    plt.ylabel(f"final PnL (mean of {len(SEEDS)} seeds)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(HERE, "final_pnl_vs_p.png"), dpi=130)
    plt.close()
    return means


# Figure 3: inventory over time, MM0 vs MM1, showing the skew at work.
def figure_inventory_over_time() -> None:
    plt.figure(figsize=(9, 5))
    for name in ("MM0", "MM1"):
        r = run_one(name, FIXED_P, seed=0)
        plt.plot(r.ticks, r.inventory, label=name, color=COLORS[name])
    plt.axhline(0, color="gray", lw=0.8, ls="--")
    plt.title(f"Inventory over time (p = {FIXED_P})")
    plt.xlabel("tick")
    plt.ylabel("inventory (shares)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(HERE, "inventory_over_time.png"), dpi=130)
    plt.close()


# Write the PnL decomposition table (averaged over seeds) to a CSV.
def write_summary() -> None:
    rows = []
    for name in ("MM0", "MM1", "MM2"):
        for p in P_VALUES:
            runs = [run_one(name, p, s) for s in SEEDS]
            keys = ("total", "spread_capture", "inventory_mtm",
                    "pnl_vs_noise", "pnl_vs_informed")
            avg = {k: np.mean([r.decomposition[k] for r in runs]) for k in keys}
            rows.append([name, p, *(round(avg[k], 1) for k in keys)])
    with open(os.path.join(HERE, "summary.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["mm", "p", "total", "spread_capture",
                    "inventory_mtm", "pnl_vs_noise", "pnl_vs_informed"])
        w.writerows(rows)
    return rows


def main() -> None:
    figure_pnl_over_time()
    means = figure_final_pnl_vs_p()
    figure_inventory_over_time()
    rows = write_summary()
    print("Final PnL vs p (mean of seeds):")
    print(f"{'p':>6} {'MM0':>10} {'MM1':>10} {'MM2':>10}")
    for i, p in enumerate(P_VALUES):
        print(f"{p:>6} {means['MM0'][i]:>10.0f} "
              f"{means['MM1'][i]:>10.0f} {means['MM2'][i]:>10.0f}")
    print("\nWrote figures and summary.csv to experiments/")


if __name__ == "__main__":
    main()
