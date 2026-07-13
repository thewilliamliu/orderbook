# Background notes

Longer-form notes I wrote while learning the material behind `orderbook-lab`, moved
out of the main [README](README.md) to keep it focused. None of this is required to
understand the code or the results — it's the conceptual grounding, in my own words.

## Table of contents
- [Why I'm doing this](#why-im-doing-this)
- [Reading](#reading)
- [Markets and limit order books](#markets-and-limit-order-books)
- [The Glosten–Milgrom model](#the-glostenmilgrom-model)
- [Notes on inventory](#notes-on-inventory)

## Why I'm doing this

My goal in this project is to deliver a GitHub repo and set of experiments that involve:
- A **matching engine** --- accepts limit orders, market orders, etc and emits trades
- A **market simulator** --- something that generates order flow from artificial participants which include "noise traders" (random orders, think your average Robinhood guy) and "informed traders" (those who can see and predict price movement, think big shops)
- A **market-making agent** --- an agent that quotes a bid, ask, earns the spread, and manages the inventory

I summarized some key points of my readings below in further detail than on the front page.

## Markets and limit order books

Any market in human history requires buyers and sellers. They must make a trade at a price that is fair to both. The goal of any market is to pool this activity in one, efficient place that allows for liquidity and price discovery.

**Liquidity**: the ease with which an asset or security can be converted into ready cash without affecting its market price
- Low demand ruins liquidity since a seller has to change the price to get it sold. Low supply also ruins liquidity since the price must go up if there are too many buyers.

**Price discovery**: the process by which the price of an asset is set -- buyers walking around and looking at sellers' asks, or sellers going around and trying to figure out buyers' bids. The latter is far harder than the former; this is often denoted *information asymmetry*.

A **limit order book** aims to solve the problem of information asymmetry. Traders can look at both buyers/sellers and immediately know what they need to know.
- There is a unique order book per stock/security.
- Each participant can place as many orders as they want -- each represents an intention to trade. Orders contain the following:
	- **side**: whether you would like to buy or sell.
	- **quantity**: how much, e.g. 100 shares
	- **limit price**: highest price you will buy / lowest price you will sell
	- **submission time**: when you sent this order in
- There are some restrictions to how one can place their orders.
	- **tick size**: the difference between price levls that you can choose from, e.g. 100, 100.5, etc
	- **lot size**: minimum quantity multiple (100, 200, 300, etc)
- The core actions you can perform as a participant are
	- Make a new order
	- Cancel an order (even midway through it being filled)
	- Amend an order (might lose you queue priority)

The order book is divided into **bid** and **ask** sides.
- Order books are sorted based on **price/time priority**. The bid-side has the highest price on top, the ask-side has the lowest price on top. That means the top of the book has the best order -- referred to as **TOB**.
	- As you go downward, you go "deeper into the book"
- The second sorting condition, time, means that the earlier-submitted order has higher priority. A *queue* is a useful data structure here, from COS 226.
- Sometimes, size and brokers are used to determine priority as well.

The **spread** is the gap between the best bid and the best ask.
- Market makers try to "earn the spread" by buying at a low price and selling at a high one -- they insert themselves into the market here and earn a few cents every time.
	- They try to be on both sides, otherwise they'll hold a bunch of shares -- "left holding the bag."
- We can also define the **mid price**, which is a useful marker for where the market is.

$$m = \text{mid price} = \frac{\text{best bid} + \text{best ask}}{2}$$

Orders can be either passive or aggressive with respect to the spread:
- **Passive**: they don't cross the market price, e.g. their $\text{limit price} < \text{best ask price}$, or their $\text{limit price} > \text{best bid price}$
	- These orders sometimes just sit there, called **resting orders**.
	- This adds liquidity since there are more shares available on the market.
- **Aggressive**: any order that crosses the spread, executing at the market price
	- This usually results in a trade or exchange -- that is, your order has been filled.
	- Another way of saying this is to "hit the bid" or "lift the ask."
	- This removes liquidity since there are less shares available on the market.

Traders just keep looping the following until nothing can be done.
1. Is the price more/equally passive than our orders' limit price?
2. Do we have quantity left to match on our order?

One order can **partially fill** another or fill multiple -- you just keep on looping. That is why it's called a **limit price**: you don't fill anything beyond it, you just fill up to it.
- Sometimes, you might be concerned with the **VWAP**: volume-weighted average price

$$\text{volume-weighted average price} = \frac{(p_1 \cdot v_1) + \dots + (p_n \cdot v_n)}{v_1 + \dots + v_n}$$

where $p_i$ and $v_i$ represent the price and volume of the $i$-th order.

**Basis points (bps)**: unit of measure for a percentage such that $1\% = 100 \text{ bps}$.

There are different ways in which people can place orders:
- **Limit order**: you have a limit price (the worst price for you) and you hope you can do a bit better than that
	- Avoids slippage -- see below.
- **Market order**: buy at whatever price is available. By definition, this is *aggressive*.
	- You have no control over what price you match at, so this is risky. If you trade a large quantity, you might encounter **slippage**: you trade against more and more people that might have greater and greater prices.
	- Slippage can be positive or negative depending on how the market is moving.
- **Stop order**: only enters the book when a certain condition is met
- **Time in Force (TIF)** also allows you to specify how long you want your order to be active for
	- Day, Good Till Cancel (GTC) are self-explanatory
	- Immediate or Cancel (IOC): if passive not aggressive, get rid of it
	- Fill or Kill Order (FOK): if order is not fully filled, cancel it

There are different levels of data, increasingly expensive and hard to stream:
- **Level 1 (L1)**: the top of the book --- the bid and the ask, quantity available at the price, what we might call the basic "quote"
- **Level 2 (L2)**: an order book with more than the top level --- list of price levels and quantities.
- **Level 3 (L3)**: an order book with all individual orders, not just aggregated
	- used by very technical quantitative trading firms and market makers

We can think about **depth of liquidity** of a market by calculating an impact price.
- **impact price**: the best bid/ask for a market order of a certain quantity
	- Suppose your quantity is 1,000 --- after executing it, what will the bid/ask be?
- a **depth chart** is U shaped
	- starts at 0 at the mid price (all trades will have been executed)
	- as you move outward, each side gains more cumulative liquidity since there are more buyers willing to buy low and more sellers willing to sell high

## The Glosten–Milgrom model

There's a pretty well-known **Glosten-Milgrom model** for market-makers that Claude told me about and I found interesting. It was also in a recent article by Matt Levine. Here is some context for that:

The GM framework says that by making money off the spread repeatedly, market makers can offset the risk of trading against informed hedge funds.
- Greater **adverse selection risk** --> greater the spread

In every period, we have three players:
1. **Market-maker**, denoted $MM$. They post bid $b$, ask $a$, and must earn at least $0$ PnL. (Even if they make no money here, they can make money elsewhere)
2. **Informed trader**, denoted $I$. They know the true price $v$. Let the chance of them showing up be denoted $\mu$.
3. **Noise trader**, denoted $N$. They are a random player and have $1 - \mu$ chance of arriving to the market.

Then, we can model their behavior:
- If $I$ sees high $v$, they buy at the ask. If $I$ sees low $v$, they sell at the bid.
- $N$ buys or sells 50-50, they're a coinflip.
- $MM$ only observes the side of the incoming order, but doesn't know $I$ vs $N$.

For simplicity, assume the true value $v$ either is $v_L$ or $v_H$, low or high respectively.

Let $q$ be the prior probability that the asset is high-valued.

$$P(v = v_H) = q$$

Then the chance an *informed* orderer makes a buy is given by
- numerator: the informed trader arrives, in which the asset *is* high valued (so he buys)
- over the total probability of observing a buy (informed trader + noise trader making a random bet with 50-50 odds)

$$P[I \mid \text{buy}] = \frac{\mu q}{\mu q + \frac{1-\mu}{2}}$$

Then we can find what our expected value really is:
- if it was an informed buy, the value is certainly $v_H$
- if it was a noise buy, we are still guessing, hence $E[v] = qv_H + (1-q)v_L$

$$E[v \mid \text{buy}] = P[I \mid \text{buy}] \, v_H + (1 - P[I\mid\text{buy}]) \, E[v]$$

As the market maker, we then need to
- charge a buyer the value we expect, conditional on a buy
- pay a seller the value we expect, conditional on a sale

$$a = E[v \mid \text{buy}] \hspace{20pt} b = E[v \mid \text{sell}]$$

Then we can get the spread

$$S = a - b = P[I\mid \text{buy}] (v_H - E[v]) + P[I\mid\text{sell}](E[v] - v_L)$$

There are two insurance premiums here on both sides depending on if the informed trader buys/sells. If there is a higher $\mu$, or probability of the trader being informed, then there is a larger spread.
- In other words, *the spread is an insurance premium against informed flow*.

## Notes on inventory

**Avellaneda and Stoikov** did a study on a stock dealer's strategy when faced with inventory risk due to stock price and Poisson arrival of market buy/sell orders.

They propose an "inventory-based" strategy.
1. Dealer computes a personal indifference valuation for stock given his current inventory.
2. Calibrates his bid/ask quotes to the market's limit order book.

In the literature, the common sources of risk facing the dealer are
1. inventory risk arising from uncertainty in the asset's value
2. asymmetric information arising from informed traders

The specific math is implemented in **part 3** of the main README.
