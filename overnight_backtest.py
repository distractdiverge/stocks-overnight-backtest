#!/usr/bin/env python3
"""
overnight_backtest.py
Paper-only research tool for the overnight vs. daytime return split
(the pattern Bruce Knuteson and Elm Wealth have written about).

For each stock, every trading day's return is split into:
    overnight = today's open  / yesterday's close
    daytime   = today's close / today's open

Three strategies are compared:
    Buy & hold      - just own it
    Overnight-only  - buy at the close, sell at the next open, every day
    Daytime-only    - buy at the open, sell at the close, every day

It reports, per ticker (plus an equal-weight basket of your picks):
    - growth, CAGR, volatility, Sharpe, max drawdown
    - after-tax ending value (overnight = short-term gains every year,
      buy & hold = long-term gain taxed once at the end)
    - break-even trading cost: how many basis points per trade it would take
      to erase the overnight edge entirely
    - year-by-year overnight vs daytime returns (is it fading?)
    - the worst overnight gaps (the risk this strategy actually carries)
    - last 1 year and last 3 years, to check whether it still holds

Nothing here connects to a broker or places trades.

SETUP (once, in Terminal):
    python3 -m venv ~/overnight-env
    source ~/overnight-env/bin/activate
    pip install yfinance pandas matplotlib

RUN:
    source ~/overnight-env/bin/activate
    python overnight_backtest.py

OPTIONS (all optional):
    --tickers NVDA AMD MU AVGO TSLA     stocks to test (SPY and QQQ are always added as benchmarks)
    --start 2010-01-01                  first date
    --end 2026-10-01                    last date (default: today)
    --cost-bps 2                        cost per trade, in basis points (1 bp = 0.01%)
    --st-tax 0.35                       your short-term (ordinary income) tax rate, federal + state
    --lt-tax 0.20                       your long-term capital gains rate, federal + state
    --csv-dir folder                    read TICKER.csv files (Date, Open, Close) instead of downloading
    --out folder                        where to save the chart and CSVs (default: overnight_results)

NOTES ON THE NUMBERS:
    - Prices are split- and dividend-adjusted (Yahoo auto_adjust). Dividends paid
      overnight are folded into the overnight return, which flatters it slightly.
    - Yahoo's "Open" is close to, but not always exactly, the official opening
      auction price. Market-on-close / market-on-open orders fill at the auction,
      so real fills should be close to these numbers for liquid stocks.
    - Cost per trade is charged twice per day (buy at close, sell at open).
    - Taxes are simplified: no wash-sale rules, no state nuance, losses carried
      forward within the strategy only. Use them to compare, not to file.
"""

import argparse
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_TICKERS = ["NVDA", "AMD", "MU", "AVGO", "TSLA"]
BENCHMARKS = ["SPY", "QQQ"]
TRADING_DAYS = 252


# ---------------------------------------------------------------- data

def load_from_yahoo(tickers, start, end):
    try:
        import yfinance as yf
    except ImportError:
        sys.exit("yfinance isn't installed. Run: pip install yfinance pandas matplotlib")
    data = {}
    for t in tickers:
        print(f"  downloading {t} ...")
        df = yf.download(t, start=start, end=end, auto_adjust=True, progress=False)
        if df is None or df.empty:
            print(f"  ! no data for {t}, skipping")
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        data[t] = df[["Open", "Close"]].dropna()
    return data


def load_from_csv(tickers, folder, start, end):
    data = {}
    for t in tickers:
        path = Path(folder) / f"{t}.csv"
        if not path.exists():
            print(f"  ! {path} not found, skipping")
            continue
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
        df = df.loc[start:end, ["Open", "Close"]].dropna()
        data[t] = df
    return data


# ---------------------------------------------------------------- returns

def split_returns(df):
    """Overnight, daytime and full-day returns from Open/Close prices."""
    prev_close = df["Close"].shift(1)
    out = pd.DataFrame({
        "overnight": df["Open"] / prev_close - 1,
        "daytime": df["Close"] / df["Open"] - 1,
    }).dropna()
    out = out[(df["Open"] > 0).reindex(out.index, fill_value=False)]
    out["full"] = (1 + out["overnight"]) * (1 + out["daytime"]) - 1
    return out


def make_basket(split_by_ticker, members):
    """Equal-weight basket, rebalanced daily, over the days all members traded."""
    members = [m for m in members if m in split_by_ticker]
    if len(members) < 2:
        return None
    parts = {}
    for col in ["overnight", "daytime"]:
        frame = pd.concat({m: split_by_ticker[m][col] for m in members}, axis=1).dropna()
        parts[col] = frame.mean(axis=1)
    out = pd.DataFrame(parts).dropna()
    # Daily rebalanced buy & hold of the basket
    full = pd.concat({m: split_by_ticker[m]["full"] for m in members}, axis=1).dropna().mean(axis=1)
    out["full"] = full.reindex(out.index)
    return out.dropna()


def strategy_returns(sr, cost):
    """Daily returns of the three strategies. cost is a fraction per trade."""
    round_trip = (1 - cost) ** 2
    return pd.DataFrame({
        "Buy & hold": sr["full"],
        "Overnight": round_trip * (1 + sr["overnight"]) - 1,
        "Daytime": round_trip * (1 + sr["daytime"]) - 1,
    })


# ---------------------------------------------------------------- metrics

def metrics(r):
    eq = (1 + r).cumprod()
    years = len(r) / TRADING_DAYS
    end_value = eq.iloc[-1]
    cagr = end_value ** (1 / years) - 1 if years > 0 and end_value > 0 else float("nan")
    sd = r.std()
    return {
        "Growth of $1": end_value,
        "CAGR": cagr,
        "Volatility": sd * math.sqrt(TRADING_DAYS),
        "Sharpe": (r.mean() / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else float("nan"),
        "Max drawdown": (eq / eq.cummax() - 1).min(),
    }


def after_tax_yearly(r, st_tax):
    """Taxed every calendar year on net gains at the short-term rate; losses carry forward."""
    value, carry = 1.0, 0.0
    for _, g in r.groupby(r.index.year):
        start = value
        value *= (1 + g).prod()
        taxable = (value - start) + carry
        if taxable > 0:
            value -= taxable * st_tax
            carry = 0.0
        else:
            carry = taxable
    return value


def after_tax_at_end(r, lt_tax):
    value = (1 + r).prod()
    gain = value - 1
    return value - gain * lt_tax if gain > 0 else value


def break_even_bps(sr):
    """Cost per trade (bps) at which overnight-only exactly matches buy & hold, pre-tax."""
    n = len(sr)
    night = (1 + sr["overnight"]).prod()
    hold = (1 + sr["full"]).prod()
    if night <= hold or n == 0:
        return 0.0
    c = 1 - (hold / night) ** (1 / (2 * n))
    return c * 1e4


def yearly_split(sr):
    g = sr.groupby(sr.index.year)
    return pd.DataFrame({
        "overnight": g["overnight"].apply(lambda x: (1 + x).prod() - 1),
        "daytime": g["daytime"].apply(lambda x: (1 + x).prod() - 1),
        "full": g["full"].apply(lambda x: (1 + x).prod() - 1),
    })


# ---------------------------------------------------------------- formatting

def pct(x, digits=1):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.{digits}f}%"


def money(x):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"${x:,.2f}"


def print_section(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


# ---------------------------------------------------------------- main

def analyze(name, sr, args, cost):
    strat = strategy_returns(sr, cost)
    rows = {k: metrics(strat[k]) for k in strat.columns}

    after_tax = {
        "Buy & hold": after_tax_at_end(strat["Buy & hold"], args.lt_tax),
        "Overnight": after_tax_yearly(strat["Overnight"], args.st_tax),
        "Daytime": after_tax_yearly(strat["Daytime"], args.st_tax),
    }

    recent = {}
    for label, days in [("Last 1y", TRADING_DAYS), ("Last 3y", 3 * TRADING_DAYS)]:
        if len(strat) >= days:
            tail = strat.iloc[-days:]
            recent[label] = {
                "Buy & hold": (1 + tail["Buy & hold"]).prod() - 1,
                "Overnight": (1 + tail["Overnight"]).prod() - 1,
            }

    worst = sr["overnight"].nsmallest(10)
    pos_nights = (sr["overnight"] > 0).mean()
    be = break_even_bps(sr)

    print_section(f"{name}   {sr.index[0].date()} to {sr.index[-1].date()}   ({len(sr)} trading days)")
    table = pd.DataFrame(rows).T
    table["After-tax $1"] = pd.Series(after_tax)
    fmt = table.copy()
    fmt["Growth of $1"] = table["Growth of $1"].map(money)
    fmt["After-tax $1"] = table["After-tax $1"].map(money)
    for col in ["CAGR", "Volatility", "Max drawdown"]:
        fmt[col] = table[col].map(pct)
    fmt["Sharpe"] = table["Sharpe"].map(lambda v: f"{v:.2f}")
    print(fmt.to_string())

    print(f"\nCost assumed: {args.cost_bps:g} bps per trade (x2 per day for overnight/daytime)")
    if be > 0:
        print(f"Break-even cost: {be:.1f} bps per trade. Above this, buy & hold wins pre-tax.")
    else:
        print("Break-even cost: none. Overnight-only lost to buy & hold even with zero costs.")
    print(f"Nights with a gain: {pct(pos_nights)}")

    for label, vals in recent.items():
        print(f"{label}: buy & hold {pct(vals['Buy & hold'])}, overnight-only {pct(vals['Overnight'])}")

    print("\nWorst 10 overnight gaps (losses you'd take holding overnight):")
    for d, v in worst.items():
        print(f"  {d.date()}  {pct(v)}")

    ys = yearly_split(sr)
    print("\nYear by year (no costs):")
    print(ys.apply(lambda col: col.map(pct)).to_string())

    summary_row = {
        "name": name,
        "start": sr.index[0].date(),
        "end": sr.index[-1].date(),
        **{f"{k} CAGR": rows[k]["CAGR"] for k in rows},
        **{f"{k} max DD": rows[k]["Max drawdown"] for k in rows},
        **{f"{k} after-tax $1": after_tax[k] for k in after_tax},
        "break-even bps": be,
        "worst overnight gap": worst.iloc[0] if len(worst) else float("nan"),
    }
    ys_out = ys.copy()
    ys_out.insert(0, "name", name)
    return strat, summary_row, ys_out


def plot(all_strats, out_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n(matplotlib not installed, skipping chart)")
        return None
    names = list(all_strats)
    cols = 2
    rows = math.ceil(len(names) / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(12, 3.6 * rows), squeeze=False)
    colors = {"Buy & hold": "#444444", "Overnight": "#1f6feb", "Daytime": "#d9822b"}
    for ax, name in zip(axes.flat, names):
        strat = all_strats[name]
        for col in strat.columns:
            ax.plot((1 + strat[col]).cumprod(), label=col, color=colors[col], linewidth=1.2)
        ax.set_yscale("log")
        ax.set_title(name)
        ax.grid(alpha=0.3)
        ax.axhline(1, color="#999999", linewidth=0.8)
    for ax in list(axes.flat)[len(names):]:
        ax.axis("off")
    axes.flat[0].legend(loc="upper left", fontsize=8)
    fig.suptitle("Growth of $1 (log scale, after trading costs, before tax)")
    fig.tight_layout()
    path = Path(out_dir) / "overnight_chart.png"
    fig.savefig(path, dpi=130)
    return path


def main():
    p = argparse.ArgumentParser(description="Overnight vs daytime return backtest (paper only).")
    p.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    p.add_argument("--start", default="2010-01-01")
    p.add_argument("--end", default=str(date.today()))
    p.add_argument("--cost-bps", type=float, default=2.0)
    p.add_argument("--st-tax", type=float, default=0.35)
    p.add_argument("--lt-tax", type=float, default=0.20)
    p.add_argument("--csv-dir", default=None)
    p.add_argument("--out", default="overnight_results")
    args = p.parse_args()

    picks = [t.upper() for t in args.tickers]
    tickers = picks + [b for b in BENCHMARKS if b not in picks]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading prices for {', '.join(tickers)} ...")
    if args.csv_dir:
        prices = load_from_csv(tickers, args.csv_dir, args.start, args.end)
    else:
        prices = load_from_yahoo(tickers, args.start, args.end)
    if not prices:
        sys.exit("No price data loaded.")

    split = {t: split_returns(df) for t, df in prices.items() if len(df) > 30}
    basket_members = [t for t in picks if t not in BENCHMARKS]
    basket = make_basket(split, basket_members)
    if basket is not None:
        split[f"BASKET ({'+'.join(m for m in basket_members if m in split)})"] = basket

    cost = args.cost_bps / 1e4
    all_strats, summaries, yearlies = {}, [], []
    for name, sr in split.items():
        strat, row, ys = analyze(name, sr, args, cost)
        all_strats[name] = strat
        summaries.append(row)
        yearlies.append(ys)

    pd.DataFrame(summaries).to_csv(out_dir / "summary.csv", index=False)
    pd.concat(yearlies).to_csv(out_dir / "yearly.csv", index_label="year")
    chart = plot(all_strats, out_dir)

    print_section("Saved")
    print(f"  {out_dir / 'summary.csv'}")
    print(f"  {out_dir / 'yearly.csv'}")
    if chart:
        print(f"  {chart}")
    print("\nPaper results only. Past patterns don't guarantee future returns.")


if __name__ == "__main__":
    main()