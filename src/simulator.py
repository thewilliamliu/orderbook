"""The simulation harness that ties the book, traders, and market maker together."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from book import OrderBook
from config import SimConfig
from fair_value import random_walk_path
from market_maker import MarketMaker
from orders import Side
from pnl import PnLTracker
from traders import informed_order, noise_order


@dataclass
class Results:
    ticks: np.ndarray          # Tick index.
    fair_value: np.ndarray     # True fair value per tick.
    mid: np.ndarray            # Observed mid price per tick.
    inventory: np.ndarray      # Market-maker inventory per tick.
    pnl: np.ndarray            # Running total PnL (marked to current fair value).
    decomposition: dict        # Final spread / inventory / adverse-selection split.
    final_pnl: float           # Final total PnL marked to the final fair value.


class Simulator:
    # Run one simulation of a market maker against generated flow.
    def run(
        self, market_maker: MarketMaker, config: SimConfig, rng: np.random.Generator
    ) -> Results:
        cfg = config
        book = OrderBook()
        tracker = PnLTracker()

        # Fair value needs k extra steps so informed traders can look ahead.
        v_path = random_walk_path(
            cfg.initial_price, cfg.sigma, cfg.n_ticks + cfg.k, rng
        )

        mm_ids: set[int] = set()
        informed_ids: set[int] = set()
        flow_window: deque[int] = deque(maxlen=cfg.flow_window)
        quote_ids: list[int] = []
        last_mid = float(cfg.initial_price)

        ticks = np.arange(cfg.n_ticks)
        mid_log = np.empty(cfg.n_ticks)
        inv_log = np.empty(cfg.n_ticks)
        pnl_log = np.empty(cfg.n_ticks)

        for t in range(cfg.n_ticks):
            v_now = v_path[t]

            # Cancel last tick's quotes before re-quoting.
            for oid in quote_ids:
                book.cancel(oid)
            quote_ids = []

            mid = book.mid()
            if mid is None:
                mid = last_mid
            flow_signal = sum(flow_window)

            bid_px, bid_sz, ask_px, ask_sz = market_maker.quote(
                mid, tracker.inventory, flow_signal
            )
            self._post_quote(book, Side.BUY, bid_px, bid_sz, mm_ids, quote_ids,
                             informed_ids, tracker, v_now, flow_window, is_mm=True)
            self._post_quote(book, Side.SELL, ask_px, ask_sz, mm_ids, quote_ids,
                             informed_ids, tracker, v_now, flow_window, is_mm=True)

            # Generate this tick's arrivals: noise flow plus a possible shark.
            n_noise = rng.poisson(cfg.lam)
            for _ in range(n_noise):
                intent = noise_order(
                    mid, rng, cfg.noise_market_prob, cfg.jitter_width, cfg.noise_size
                )
                self._submit_intent(book, intent, False, mm_ids, informed_ids,
                                    tracker, v_now, flow_window)
            if rng.random() < cfg.p:
                intent = informed_order(
                    mid, v_path[t + cfg.k], cfg.threshold, cfg.informed_size
                )
                if intent is not None:
                    self._submit_intent(book, intent, True, mm_ids, informed_ids,
                                        tracker, v_now, flow_window)

            current_mid = book.mid()
            if current_mid is not None:
                last_mid = current_mid
            mid_log[t] = last_mid
            inv_log[t] = tracker.inventory
            pnl_log[t] = tracker.total_pnl(v_now)

        final_value = float(v_path[cfg.n_ticks - 1])
        return Results(
            ticks=ticks,
            fair_value=v_path[: cfg.n_ticks],
            mid=mid_log,
            inventory=inv_log,
            pnl=pnl_log,
            decomposition=tracker.decompose(final_value),
            final_pnl=tracker.total_pnl(final_value),
        )

    # Post one side of the market maker's quote and record any immediate fills.
    def _post_quote(self, book, side, price, size, mm_ids, quote_ids,
                    informed_ids, tracker, v_now, flow_window, is_mm):
        if size <= 0:
            return
        oid, trades = book.submit_limit(side, price, size)
        mm_ids.add(oid)
        quote_ids.append(oid)
        self._record_fills(trades, side, is_mm, mm_ids, informed_ids,
                           tracker, v_now, flow_window, update_flow=False)

    # Submit a trader's order, tag it if informed, and record fills and flow.
    def _submit_intent(self, book, intent, informed, mm_ids, informed_ids,
                       tracker, v_now, flow_window):
        if intent.is_market:
            oid, trades = book.submit_market(intent.side, intent.size)
        else:
            oid, trades = book.submit_limit(intent.side, intent.price, intent.size)
        if informed:
            informed_ids.add(oid)
        self._record_fills(trades, intent.side, False, mm_ids, informed_ids,
                           tracker, v_now, flow_window, update_flow=True)

    # Attribute trades to the market maker and update the signed-flow window.
    def _record_fills(self, trades, aggressor_side, aggressor_is_mm, mm_ids,
                      informed_ids, tracker, v_now, flow_window, update_flow):
        for tr in trades:
            if update_flow:
                signed = tr.quantity if aggressor_side is Side.BUY else -tr.quantity
                flow_window.append(signed)
            if tr.sell_id in mm_ids:
                informed = tr.buy_id in informed_ids
                tracker.record(tr.price, tr.quantity, Side.SELL, v_now, informed)
            elif tr.buy_id in mm_ids:
                informed = tr.sell_id in informed_ids
                tracker.record(tr.price, tr.quantity, Side.BUY, v_now, informed)
