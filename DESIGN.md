# DESIGN.md — orderbook-lab

> This doc is written to be *read and understood*, not just skimmed. Every design
> choice comes with the reasoning, and every formula comes with a plain-language
> explanation of what it actually means. If you can explain this doc out loud, you can
> defend the project in an interview.

## What we are building, in one breath
An **exchange** (a limit order book that matches buyers and sellers), a **fake market**
of traders to send it orders, and a **market maker** that tries to earn money by
quoting prices — and then a measurement of exactly how and why that market maker makes
or loses money. The measurement is the point; the code just makes the measurement
possible.

---

## 1. Domain objects (the vocabulary)

A "domain object" is a data structure that represents a real *thing* in the problem —
a noun a trader would recognize — as opposed to internal machinery. Our two nouns are
the **order** (someone wants to buy or sell) and the **trade** (two orders matched).

```python
from enum import Enum
from dataclasses import dataclass

class Side(Enum):
    BUY = 1
    SELL = 2

@dataclass
class Order:
    id: int          # unique label for this order, assigned by the caller (client order id)
    side: Side       # BUY or SELL
    price: int       # in integer ticks; a market order is handled without a resting price
    quantity: int    # shares remaining (shrinks as the order fills)
    seq: int         # arrival counter (see below) — establishes time priority

@dataclass
class Trade:
    buy_id: int      # the order id on the buy side of this match
    sell_id: int     # the order id on the sell side
    price: int       # the RESTING order's price (explained in §4)
    quantity: int    # shares that changed hands
    seq: int
```

**Why `@dataclass`?** It's Python shorthand for "a class that mostly just holds named
fields." Writing `@dataclass` above `Order` auto-generates the boilerplate (the
constructor, a readable `repr`, equality checks) so we don't hand-write it. It's the
clean way to say "this object *is* its data."

**Why `Side` is an `Enum`.** We could use the strings `"BUY"`/`"SELL"`, but then a typo
like `"Buy"` silently breaks a comparison. An enum is a fixed set of named constants —
`Side.BUY` either exists or the program won't run — so typos become crashes, not silent
bugs.

**Why prices are integers (ticks), not floats.** Real prices move in fixed steps (a
penny, a tick), so `10.01` is really "1001 ticks." If you store prices as floating-point
decimals you inherit binary rounding error: in a computer, `0.1 + 0.2` is *not exactly*
`0.3`. Our engine constantly asks "is this price equal to the best ask?" and uses prices
as dictionary keys — both break when two values that *should* be equal differ in the
15th decimal. Integers compare exactly and hash reliably. We divide by the tick size
only when displaying a price to a human.

**Why `seq` is a counter, not a clock.** `seq` records *arrival order*: order #5 came
before order #8, guaranteed, because the number only ever goes up (this is what
"monotonically increasing" means — never decreases, never repeats). We need this
because within one price level, orders fill in the order they arrived ("time
priority"). Why a counter instead of a wall-clock timestamp? Two orders can land in the
same microsecond and get *identical* clock times — now you can't tell which was first.
A counter you bump by 1 on every order can never tie, is deterministic (same seeded run
→ same numbers every time), and is exactly what real exchanges use. (Named `seq`, not
`timestamp`, so nobody mistakes it for a date.)

---

## 2. The book's public API (its surface)

```python
class OrderBook:
    def submit_limit(self, order_id, side, price, quantity) -> list[Trade]
    def submit_market(self, order_id, side, quantity)       -> list[Trade]
    def cancel(self, order_id: int)                         -> bool   # raises KeyError on unknown/filled id
    def best_bid(self) -> int | None    # highest price a buyer is currently willing to pay
    def best_ask(self) -> int | None    # lowest price a seller is currently willing to accept
    def mid(self)      -> float | None   # midpoint = (best_bid + best_ask) / 2
    def spread(self)   -> int | None     # best_ask − best_bid
```

The **caller supplies `order_id`** (a "client order id" — realistic, and it's the handle
you later hand to `cancel`); the exchange assigns the arrival `seq` internally. Each
`submit_*` call returns the list of trades it caused (empty if it just rested without
matching). `cancel` **raises `KeyError`** on an unknown or already-filled id (per test
#7). The **spread** is `best_ask − best_bid`; the **mid** is the point halfway between
them and is the market's best public guess of the price.

---

## 3. Data structures, and why each one

This is the "COS 226" heart of Part A: pick structures whose strengths match what the
code actually does most often.

| Concern | Choice | Why |
| --- | --- | --- |
| Order queue within one price level | `collections.deque` | Time priority for free: new orders `append` to the back, matches `popleft` from the front. Both ends are O(1). |
| Find the level for a given price | `dict[int, deque]`, one dict per side | O(1): `bids[100]` jumps straight to the queue of orders resting at 100. |
| Find the *best* price (naive, v1) | a sorted `list` of active prices | Simplest thing that works. O(n) to insert. **Build and test this first.** |
| Find the best price (optimized, v2) | `heapq`: max-heap of bids, min-heap of asks, with **lazy deletion** | O(log n) push/pop. Benchmark v1 vs v2 on 1M orders; record the speedup. |
| Cancel by id | `dict[int, Order]` mapping id → order | O(1) to locate; remove it and let the matcher continue. |

**What a `deque` is and why it fits.** A deque ("deck") is a double-ended queue — a line
you can add to or remove from at *either* end cheaply. A price level is literally a line
of orders waiting their turn: newcomers join the back, the front gets served first. A
plain Python `list` can append to the back fine, but removing from the *front*
(`list.pop(0)`) is slow — O(n) — because every remaining element shifts down one slot.
Over millions of orders that's the difference between fast and unusable. The deque does
both ends in O(1).

**Why the dict returns a deque (the two-layer picture).** At a single price there can be
many orders from different traders. So the structure is two levels deep:

```
price 100 → deque[ order#5 (50sh), order#9 (20sh), order#14 (80sh) ]   ← the queue at 100
price 101 → deque[ order#7 (200sh) ]
price 102 → deque[ order#3 (10sh),  order#11 (60sh) ]
```

The **dict** is the outer layer ("given a price, find its queue fast"); the **deque** is
the inner layer ("keep that queue in arrival order"). When the last order at a price
fills, that price's deque goes empty and we delete the key — an empty level shouldn't
linger.

**What a heap is, and "lazy deletion."** A heap is a structure that keeps the
*best* item instantly reachable at its top, at O(log n) cost to insert or remove the
top — perfect for "what's the best bid/ask right now?" Python's `heapq` is a *min*-heap
(smallest on top), which is exactly right for asks (best ask = lowest price). For bids
we want the *highest* on top, so we store bid prices negated and the min-heap surfaces
the largest real price. The catch: a heap only lets you cheaply remove the *top*, not
some element buried in the middle. So in the optimized version, when a price level
empties, instead of hunting it down and surgically removing it (O(n)), we **leave it in
the heap and skip it when it eventually floats to the top** ("oh, this level is empty —
discard and pop the next"). That's *lazy deletion*: you defer the cleanup until it's
cheap. (The naive v1 keeps things simple and removes eagerly; lazy deletion is the A.5
optimization.)

---

## 4. Matching logic (how orders actually trade)

`submit_limit(order_id, side, price, qty)`:
1. **While** the incoming order still has quantity **and** it "crosses" the opposite
   best price — a buy crosses when `price >= best_ask`; a sell crosses when
   `price <= best_bid` — keep matching:
   - Take the best opposite level, and within it the oldest order (front of the deque).
   - Emit a `Trade` at the **resting order's price** (see the box below).
   - Reduce both quantities; when the resting order hits 0, `popleft` it; when the level
     empties, drop it.
2. Whatever quantity remains **rests**: it's appended to its own side's deque (creating
   the level if new) and registered in the id → order dict.

> **The price-improvement rule (the bug test #2 exists to catch).** Say the best ask is
> resting at 100 and you send a buy limit at 105. You're *willing* to pay up to 105 —
> but you don't have to, because someone is already offering to sell at 100. The resting
> order set the terms; you're just crossing the spread to take it. So the trade prints
> at **100**, and you got "price improvement" of 5. The resting order's price always
> wins because it was there first. If you mistakenly fill at the aggressor's 105, the
> seller pockets 5 they never asked for — the classic order-book bug.

`submit_market(order_id, side, qty)`: same walk, but step 2 is skipped. A market order
says "fill me *now* at any price" — it has no price of its own. So if it exhausts the
available liquidity with quantity left over, that remainder is **discarded** (the
immediate-or-cancel behavior of real venues). We don't rest it, because resting a market
order would silently invent a price it never had. We don't error either — we just fill
what we can.

`cancel(order_id)`: look it up in the id → order dict. If it's live, remove it from its
level (and drop the level/price if it becomes empty). For an *unknown or already-filled*
id we **raise `KeyError`** — a defined, clean exception (test #7). Rationale: cancelling
an id the book has never heard of is a caller bug worth surfacing loudly, and a filled
order has already left the book. (A bool-returning variant is defensible for a live
trading loop; we chose to raise to match the test spec.)

**Partial fills** fall out for free: incoming 100 vs. resting 60 → one `Trade` of 60,
the resting order is removed, and the incoming order continues with 40 still to fill.

---

## 5. What we are explicitly NOT building (yet)
- **Networking / an order gateway** — the API is plain in-process function calls.
- **Persistence** — the book lives in memory; no saving, no crash recovery.
- **Multiple instruments / options** — one book, one thing to trade.
- **Exotic order types** — no stop, iceberg, fill-or-kill, post-only. Just limit,
  market, cancel.
- **A fancy price model** — the fair value is a simple random walk for now; Assignment 2
  upgrades it, and §6 is built so that's a one-function swap.

Naming what you're *not* doing is a design skill: it shows the scope was a choice.

---

## 6. The market simulator (Part B)

An exchange with nobody trading on it does nothing. The simulator is a **synthetic
world of traders** that sends orders into the book so we can test a market maker against
it — a flight simulator for trading. Its superpower is that it *knows two secrets no
real market reveals*: the true fair value, and which traders are informed. Those two
secrets are exactly what make the final PnL measurement possible.

### 6.1 The two secrets

**Secret 1 — the "true" fair value $V$.** Imagine every stock has a correct price that
reflects all real information. In reality nobody knows it exactly. In our sim, *we*
define it and let it wander randomly over time. $V$ is our **scoring yardstick**: to ask
"did the market maker buy cheap or expensive?" we compare its trade price against $V$.
Crucially, *nobody inside the sim sees $V$* — not even the market maker. It's our
god's-eye view, used only for measurement.

**Secret 2 — who is informed.** Two kinds of fake traders send orders (below). We know
which is which and tag them, so at the end we can measure exactly how much the market
maker lost to the informed ones. A real firm would kill for this label; we have it
because we built the world.

### 6.2 Components & interfaces

```python
# src/fair_value.py
def random_walk_step(V, sigma, rng) -> float          # produces the next V

# src/traders.py
def make_noise_order(mid, rng) -> OrderIntent          # a random, uninformed order
def make_informed_order(mid, future_V) -> OrderIntent | None   # an order that knows the future

# src/simulator.py
class Simulator:
    def run(self, market_maker, n_ticks, config, rng) -> ResultLog
```

`OrderIntent` is a small "I want to place this order" description (side, is_market,
price, size); the simulator turns it into a real `Order` (assigning the id and `seq`).
`ResultLog` collects the per-tick arrays ($V$, mid, inventory, cash, tagged trades) that
the experiment plots.

### 6.3 A short probability primer (this answers "Poisson vs. normal")

We need randomness for two *different kinds of question*, and each kind uses a different
distribution. A "distribution" is just a rule for how likely each possible value is.

**The Normal (Gaussian) distribution answers "how big?"** It describes a *continuous
magnitude* — any real number — that clusters around an average, with small deviations
common and large ones rare. It's the bell curve, and it's symmetric (equally likely to
be above or below the average). Two knobs: the mean (center) and $\sigma$ (how wide the
bell). We use it for the **size of each price move** — the price can drift up or down by
any amount, usually a little, occasionally a lot.

**The Poisson distribution answers "how many?"** It describes a *count of events* — 0,
1, 2, 3, … — that happen independently at some average rate over a fixed interval. It
can't be negative (you can't have −2 events), it's a whole number (you can't have 2.5
events), and it's lopsided rather than a symmetric bell. One knob: $\lambda$ (lambda),
the average count. We use it for the **number of orders that arrive in one tick**.

> The one-line intuition: **Normal = a measured magnitude (how far?); Poisson = a tally
> of events (how many?).** Rain makes it concrete: how many *inches* fell is a
> continuous magnitude → Normal-ish; how many *raindrops* hit one roof tile in a second
> is a count of discrete events → Poisson. Our price *jump size* is inches; our *order
> count per tick* is raindrops. That's why they use different distributions.

### 6.4 The stochastic pieces, spelled out

**Fair value — the random walk.**

$$
V(t+1) = V(t) + \sigma \cdot \varepsilon_t, \qquad \varepsilon_t \sim \text{Normal}(0, 1)\ \text{independently each tick}
$$

Read it left to right: "next tick's fair value = this tick's, plus a random nudge." The
nudge is $\sigma \cdot \varepsilon_t$. Here $\varepsilon_t$ ("epsilon") is a fresh draw
from the standard bell curve — usually near 0, sometimes ±1 or ±2 — and $\sigma$
("sigma", volatility) scales it into price units. Big $\sigma$ = wild market; small
$\sigma$ = calm. This is a **Normal**, used for "how big is the move." Two properties
matter:

- *It's a martingale:* $\mathbb{E}[V(t+1) \mid V(t)] = V(t)$ — "the **expected** next
  value, given where we are now, equals where we are now." Because each nudge averages
  to zero, your best guess of tomorrow's price is today's price. This is *why* uninformed
  traders can't systematically win and the market maker can safely earn the spread off
  them — nobody who only sees the past has an edge. Only someone who sees the actual
  future nudge (the informed trader) can beat it.
- *Uncertainty grows like $\sqrt{\text{time}}$:* $\text{Var}\big(V(t) - V(0)\big) = t
  \cdot \sigma^2$, so the typical wander over $t$ ticks is about $\sigma\sqrt{t}$. (Var =
  variance, the spread-out-ness; its square root is the typical size.) That $\sqrt{t}$
  is why a longer-lookahead informed trader has a bigger edge.

**Order arrivals — Poisson.** The number of noise orders in one tick is

$$
N \sim \text{Poisson}(\lambda), \qquad P(N = n) = \frac{e^{-\lambda}\, \lambda^n}{n!}, \qquad \mathbb{E}[N] = \lambda.
$$

Read $N \sim \text{Poisson}(\lambda)$ as "$N$ is drawn from a Poisson with average
$\lambda$." The formula gives the probability of exactly $n$ orders: e.g. with $\lambda =
2$ you'll usually see 1–3 orders, sometimes 0, occasionally 5. $\lambda$ is just **how
busy the market is**. Equivalent continuous view: the *gap* between consecutive arrivals
is Exponential, drawn in code as `rng.exponential(1/λ)` — that single line is 90% of
"simulating a Poisson process." We use the per-tick *count* form because it's simpler to
loop over and reproducible under a fixed seed.

**Informed trader — where the edge comes from.** At tick $t$ the informed trader peeks
at $V(t+k)$ — the fair value $k$ ticks in the future — and compares it to the current
visible mid $m$:

$$
\begin{cases}
\text{market BUY}  & \text{if } V(t+k) - m > \theta \quad (\text{price heading up} \to \text{grab shares now}) \\
\text{market SELL} & \text{if } V(t+k) - m < -\theta \\
\text{do nothing}  & \text{otherwise (no worthwhile edge)}
\end{cases}
$$

Its expected profit per trade is roughly $\mathbb{E}\,|V(t+k) - m|$, which (from the
$\sqrt{t}$ fact above) scales like $\sigma\sqrt{k}$. So $p$ — the probability an informed
trader shows up on a given tick — controls *how often* sharks appear, while $(\sigma, k)$
control *how sharp* each one is. $\theta$ ("theta") is an optional threshold so it only
trades when the edge clears the spread. $p$ is our single "adverse-selection dial" and
lives in config.

**Noise traders, and what "jitter" means.** A noise trader is uninformed: random side
(buy/sell is a coin flip), and with probability $q$ it sends a market order, otherwise a
limit order. When it posts a *limit* order it must choose a price — and here's the jitter
part:

$$
\text{limit price} = \text{round}(m + \text{jitter}), \qquad \text{jitter} \sim \text{Uniform}\{-W, \dots, +W\}\ \text{ticks}
$$

**"Jitter" is just a small random wiggle added to the mid so the order doesn't land
exactly at the midpoint.** Why bother? A real order book has resting orders stacked at
*many* nearby prices — a ladder of bids below the mid and asks above it, giving the book
depth:

```
      asks:  103 (12sh)
             102 (30sh)
             101 (8sh)     ← best ask
   mid ~100.5
             100 (15sh)    ← best bid
       bids:  99 (40sh)
              98 (22sh)
```

If every noise order used *exactly* the mid, all orders would pile onto one price and
there'd be no ladder — an unrealistic book with no depth for the market maker to
interact with. By scattering ("jittering") each order a few ticks off the mid, the noise
traders naturally build that realistic ladder. $W$ sets how wide the scatter — how deep
into the book noise reaches.

### 6.5 Tagging informed flow
The simulator keeps a `set[int]` of the order ids belonging to informed traders. We
deliberately **do not** put an "informed" field on the `Order` object — the exchange has
no way to know who's informed (neither does a real one), and we want to respect that.
The experiment reads the tag afterward to attribute losses.

### 6.6 The per-tick loop (order of operations matters)
1. Advance the fair value → $V(t)$.
2. The market maker looks at the book (mid, recent flow), **cancels its old quotes**,
   and posts a fresh bid and ask. *(This must happen before the flow arrives, or it's
   quoting on stale prices.)*
3. Generate this tick's arrivals — the noise orders, plus maybe one informed order — and
   feed them into the book in arrival order. They trade against the market maker's
   resting quotes (and each other).
4. Log everything: trades (with the informed tag), $V$, mid, the market maker's
   inventory, and its cash.

---

## 7. The market makers & the experiment (Part C)

### 7.1 What a market maker does
A market maker posts two prices continuously: a **bid** (I'll buy at 99) and an **ask**
(I'll sell at 101). It's a shopkeeper — buys wholesale at its bid, sells retail at its
ask, keeps the difference (the spread). If a random buyer lifts its ask at 101 and a
random seller hits its bid at 99, it earns 2 and holds nothing. That's the dream.

Two things threaten it. **Inventory:** if it keeps buying, it piles up a big long
position and is exposed if the price drops. **Adverse selection:** if the trader who
bought from it was *informed*, the price is about to run up, and the market maker — now
short — has to buy back higher and loses. Our three market makers get progressively
smarter about these two threats. They all share one interface:

```python
# src/market_maker.py
class MarketMaker:
    def quote(self, mid, inventory, flow_signal) -> (bid_px, bid_sz, ask_px, ask_sz)
    # px = price, sz = size (shares)
```

Every one of them quotes around the **visible mid**, never $V$ — a market maker can't
see the future.

| Agent | Rule | Knobs |
| --- | --- | --- |
| **MM-0** naive | quote symmetrically around the mid, fixed size | $h$ |
| **MM-1** inventory-aware | shift both quotes against inventory | $h, \gamma$ |
| **MM-2** toxicity-aware | MM-1 **plus** widen the spread when flow is one-sided | $h, \gamma, \beta$ |

### 7.2 The quoting math, spelled out

**MM-0** has no memory. With half-spread $h$ (half the total gap):

$$
\text{bid} = m - h, \qquad \text{ask} = m + h.
$$

Wider $h$ = more profit per fill but fewer fills, since its prices are less attractive.
That's the only lever.

**MM-1 — inventory skew.** Instead of centering its quotes on the mid $m$, it centers
them on a shifted **reservation price** $r$:

$$
r = m - \gamma \cdot I, \qquad \text{bid} = r - h, \qquad \text{ask} = r + h,
$$

where $I$ is current inventory. Walk through it: if $I > 0$ (holding a long position it
wants to shed), then $r < m$, so *both* quotes move down. A lower ask is more attractive
to buyers, so it sells the position off; a lower bid is less attractive to sellers, so it
stops accumulating more. The skew gently pushes inventory back toward zero. $\gamma$
("gamma") is **inventory aversion** in price-per-share: crank it up and it fights harder
to stay flat, but it quotes further from the mid and captures less spread — a dial
between *inventory risk* and *spread income*. (This is the Avellaneda–Stoikov intuition,
reservation price shifts with inventory, without any of the calculus.)

**MM-2 — toxicity widening.** It watches the recent **signed order flow** over the last
$L$ trades, adding up sizes with a sign for direction:

$$
f = \sum_{\text{recent trades}} \pm\,(\text{size}), \qquad
\begin{cases} +\,\text{size} & \text{buyer-initiated (a market buy lifting the ask)} \\ -\,\text{size} & \text{seller-initiated} \end{cases}
$$

A large positive $f$ means a wave of buying — possibly informed buyers, and the market
maker is the one selling into that wave (going short right before an up-move). Its
defense is to widen the spread when flow is lopsided:

$$
h_{\text{eff}} = h + \beta \cdot |f|.
$$

So MM-2 uses MM-1's skew *and* this wider $h_{\text{eff}}$. $\beta$ ("beta") is
**toxicity sensitivity** — how sharply it recoils from one-sided flow. (A natural
extension, worth a README note: widen only the side being attacked, asymmetrically,
instead of both.)

### 7.3 The PnL decomposition — the whole point of the project

**Notation.** Index the market maker's fills by $i$. For each fill let $P_i$ be the
executed price, $V_i$ the true fair value *at that instant*, and $q_i$ the size. Give the
size a sign:

$$
s_i = \begin{cases} +q_i & \text{if the MM sold} \\ -q_i & \text{if the MM bought} \end{cases}
$$

A sell lowers inventory and a buy raises it, so the inventory change on fill $i$ is
$\Delta I_i = -s_i$. Let $V_T$ be the fair value at the end of the run.

**Total PnL.** Cash rises by $P_i q_i$ on a sell and falls by $P_i q_i$ on a buy — both
captured by the single term $P_i s_i$. Leftover inventory is marked to the final fair
value. So

$$
\Pi \;=\; \underbrace{\sum_i P_i s_i}_{\text{cash}} \;+\; \underbrace{\Big(-\sum_i s_i\Big)}_{\text{final inventory}} V_T \;=\; \sum_i s_i \,(P_i - V_T).
$$

**The split.** Add and subtract $V_i$: since $P_i - V_T = (P_i - V_i) + (V_i - V_T)$,

$$
\Pi \;=\; \underbrace{\sum_i s_i\,(P_i - V_i)}_{\textbf{spread capture}} \;+\; \underbrace{\sum_i s_i\,(V_i - V_T)}_{\textbf{inventory MTM}}.
$$

The two terms reconstruct the total **exactly** — no residual. What each means:

- **Spread capture**, $s_i(P_i - V_i)$: the edge *at the instant of the trade*. Selling
  above fair ($P_i > V_i,\ s_i > 0$) or buying below fair ($P_i < V_i,\ s_i < 0$) both
  come out positive. Answers "did I quote a sensible spread?"
- **Inventory MTM**, $s_i(V_i - V_T)$: what the market did to the position *afterward*.
  It equals $\Delta I_i (V_T - V_i)$, so long-into-a-rise gains and short-into-a-rise
  loses. Answers "did the market run me over after I traded?"

**Adverse selection** is simply the inventory-MTM term restricted to fills against
informed traders (tagged in §6.5):

$$
\text{Adverse-selection loss} \;=\; \sum_{i \,\in\, \text{informed}} s_i\,(V_i - V_T).
$$

It comes out sharply negative, because informed traders trade *precisely* when $V_i \to
V_T$ moves against the resulting position.

**Worked examples** ($V_i = 100$ at the fill, every size 10). The spread column is $+10$
in every row — the market maker always earns its quoted edge at the instant of the
trade. The *entire* difference between a good outcome and a bad one is the inventory-MTM
column, which depends only on whether the counterparty was informed:

| MM action | Counterparty | $V_T$ | Spread $s_i(P_i - V_i)$ | Inv MTM $s_i(V_i - V_T)$ | Net |
| --- | --- | --- | --- | --- | --- |
| Sell @ 101 ($s_i=+10$) | noise | 100 | $+10(101-100)=+10$ | $+10(100-100)=0$ | **+10** |
| Sell @ 101 ($s_i=+10$) | shark (price rises) | 105 | $+10$ | $+10(100-105)=-50$ | **−40** |
| Buy @ 99 ($s_i=-10$) | noise | 100 | $-10(99-100)=+10$ | $-10(100-100)=0$ | **+10** |
| Buy @ 99 ($s_i=-10$) | shark (price falls) | 95 | $-10(99-100)=+10$ | $-10(100-95)=-50$ | **−40** |

**That contrast is the project.** `PnLTracker` in `src/pnl.py` just does the
`cash`/`inventory` bookkeeping during the run and reports these sums, split by the tag.

### 7.4 Required figures (saved to `experiments/` by `run_experiment.py`)
1. **PnL over time** for MM-0/1/2 at a fixed $p$ — one chart, three lines.
2. **The money chart:** final PnL vs. $p \in \{0, 0.05, 0.1, 0.2\}$, one line per market
   maker. MM-0's line should dive as $p$ rises; MM-2's should degrade gracefully. This is
   the chart that goes at the top of the README — people decide in 10 seconds.
3. **Inventory over time**, MM-0 vs. MM-1 — you should *see* MM-1's skew pulling its
   inventory back toward flat while MM-0's wanders.

### 7.5 A limitation to state honestly (in the README)
Our informed traders are **omniscient** — they see $V(t+k)$ perfectly. Real toxicity is
statistical and noisy, so MM-2's toxicity detector has an easier job here than it would
in reality, and the result somewhat *overstates* its advantage. Say so plainly. An
honestly-caveated result reads far better than a suspiciously clean one.

---

## 8. Reproducibility
Every random draw comes from one injected generator, `np.random.default_rng(seed)` —
never a bare `np.random.*` call. Same seed → byte-for-byte identical run. This is a
genuine selling point in the README: anyone can clone the repo and reproduce every
figure exactly.
