#!/usr/bin/env python3
"""
infra_backtest.py
Paper-only research tool: AI-infrastructure stocks, tested by layer, with
your own ethics screen. Nothing here connects to a broker or places trades.

WHAT IT TESTS
  Each infrastructure layer (chips, chip equipment, networking, power and
  cooling, utilities and nuclear, data centers, clean power) is tested as an
  equal-weight basket, plus each stock on its own, plus SPY and QQQ.

  Three strategies on each:
    Buy & hold   just own it
    Trend        own it only while it's above its 200-day moving average,
                 otherwise sit in cash (earning --cash-yield). Signal is read
                 at one day's close and traded at the next day's open, so
                 there is no peeking ahead.
    Overnight    buy at the close, sell at the next open, every day

  It also reports "Day avg": the average open-to-close move in basis points.
  Negative means buying at the close has tended to be cheaper than buying
  at that morning's open, which is useful for timing ordinary purchases.

ETHICS SCREEN (universe.csv)
  The first run writes universe.csv next to this script. Edit it in any
  spreadsheet app. Columns:
    ticker, name, layer, status, notes
  status is one of:
    approved   passes your screen
    grey       case-by-case; still tested, flagged in the output
    review     not yet evaluated (the default for every row)
    excluded   never loaded or tested
  Add or remove rows freely; the layer column decides which basket a stock
  joins. Use --only-approved to test approved stocks only.

  Where to check a company against your rules:
    - its annual report (10-K / 20-F), segment and customer sections, for
      defense or government revenue
    - USAspending.gov, search the company as a federal contract recipient
      and filter by Department of Defense
    - OpenSecrets.org, corporate PAC and executive political giving
    - investigate.afsc.org, AFSC's database of companies tied to Israeli
      occupation, prisons, and border militarization
  Record what you found in the notes column so future runs carry it.

SETUP (once, in Terminal):
    python3 -m venv ~/overnight-env
    source ~/overnight-env/bin/activate
    pip install yfinance pandas matplotlib

RUN:
    source ~/overnight-env/bin/activate
    python infra_backtest.py

OPTIONS (all optional):
    --universe universe.csv     your ethics-screened stock list
    --only-approved             test only rows marked approved
    --start 2010-01-01          first date (stocks that listed later start later)
    --end 2026-10-05            last date (default: today)
    --trend-days 200            moving-average length for the trend exit
    --cash-yield 0.03           annual yield while out of the market; set to
                                the current 3-month Treasury bill yield
    --cost-bps 2                cost per trade, basis points (1 bp = 0.01%)
    --st-tax 0.35               short-term (ordinary income) rate, fed + state
    --lt-tax 0.20               long-term capital gains rate, fed + state
    --detail-tickers            print the full report for every stock too
    --csv-dir folder            read TICKER.csv files (Date, Open, Close)
                                instead of downloading
    --out folder                output folder (default: infra_results)

NOTES ON THE NUMBERS
  - Prices are split- and dividend-adjusted (Yahoo auto_adjust).
  - Baskets are equal-weight and rebalanced daily with no rebalancing cost,
    over whichever members were trading on each day.
  - Taxes are simplified. Overnight: net gains taxed yearly at the short-term
    rate. Trend: each round trip taxed at exit, long-term if held a year or
    more, otherwise short-term, with losses carried forward. Buy & hold: taxed
    once at the end at the long-term rate. Positions still open at the end
    are taxed as if sold. Cash interest isn't taxed separately. Use these
    to compare strategies, not to file.
  - Several of these companies listed recently (GE Vernova 2024,
    Constellation 2022, Vertiv 2020), so their history is short. Short
    histories make every result less reliable.
"""

import argparse
import math
import sys
from datetime import date
from pathlib import Path

import pandas as pd

BENCHMARKS = ["SPY", "QQQ"]
TRADING_DAYS = 252
STATUSES = ["approved", "grey", "review", "excluded"]

DEFAULT_UNIVERSE = [
    # ticker, name, layer
    ("NVDA", "Nvidia", "chips_memory"),
    ("AVGO", "Broadcom", "chips_memory"),
    ("AMD", "Advanced Micro Devices", "chips_memory"),
    ("MU", "Micron", "chips_memory"),
    ("TSM", "TSMC (ADR)", "chips_memory"),
    ("ASML", "ASML (ADR)", "chip_equipment"),
    ("AMAT", "Applied Materials", "chip_equipment"),
    ("LRCX", "Lam Research", "chip_equipment"),
    ("ANET", "Arista Networks", "networking_optics"),
    ("COHR", "Coherent", "networking_optics"),
    ("CIEN", "Ciena", "networking_optics"),
    ("VRT", "Vertiv", "power_cooling"),
    ("ETN", "Eaton", "power_cooling"),
    ("GEV", "GE Vernova", "power_cooling"),
    ("CEG", "Constellation Energy", "utilities_nuclear"),
    ("VST", "Vistra", "utilities_nuclear"),
    ("EQIX", "Equinix", "data_centers"),
    ("DLR", "Digital Realty", "data_centers"),
    ("NEE", "NextEra Energy", "clean_power"),
    ("FSLR", "First Solar", "clean_power"),
]


# ================================================================ universe

def load_universe(path):
    path = Path(path)
    if not path.exists():
        rows = [{"ticker": t, "name": n, "layer": l, "status": "review", "notes": ""}
                for t, n, l in DEFAULT_UNIVERSE]
        pd.DataFrame(rows).to_csv(path, index=False)
        print(f"Wrote a starter {path}. Every stock is marked 'review' until you evaluate it.")
    u = pd.read_csv(path, dtype=str).fillna("")
    u.columns = [c.strip().lower() for c in u.columns]
    missing = {"ticker", "layer", "status"} - set(u.columns)
    if missing:
        sys.exit(f"{path} is missing columns: {', '.join(sorted(missing))}")
    if "name" not in u.columns:
        u["name"] = ""
    if "notes" not in u.columns:
        u["notes"] = ""
    u["ticker"] = u["ticker"].str.strip().str.upper()
    u["layer"] = u["layer"].str.strip()
    u["status"] = u["status"].str.strip().str.lower()
    bad = u[~u["status"].isin(STATUSES)]
    if not bad.empty:
        sys.exit(f"Unknown status for {', '.join(bad['ticker'])}. Use one of: {', '.join(STATUSES)}")
    u = u[u["ticker"] != ""].drop_duplicates("ticker")
    return u


# ================================================================ data

def load_from_yahoo(tickers, start, end):
    try:
        import yfinance as yf
    except ImportError:
        sys.exit("yfinance isn't installed. Run: pip install yfinance pandas matplotlib")
    data = {}
    for t in tickers:
        print(f"  downloading {t} ...")
        try:
            df = yf.download(t, start=start, end=end, auto_adjust=True, progress=False)
        except Exception as e:  # network hiccups shouldn't kill the whole run
            print(f"  ! {t} failed: {e}")
            continue
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
        data[t] = df.loc[start:end, ["Open", "Close"]].dropna()
    return data


# ================================================================ returns

def split_returns(df):
    """Overnight and daytime returns; full = the two compounded."""
    prev_close = df["Close"].shift(1)
    out = pd.DataFrame({
        "overnight": df["Open"] / prev_close - 1,
        "daytime": df["Close"] / df["Open"] - 1,
    }).dropna()
    out = out[(df["Open"].reindex(out.index) > 0) & (prev_close.reindex(out.index) > 0)]
    out["full"] = (1 + out["overnight"]) * (1 + out["daytime"]) - 1
    return out


def make_basket(split, members):
    """Equal-weight over whichever members traded each day."""
    members = [m for m in members if m in split]
    if not members:
        return None
    on = pd.concat({m: split[m]["overnight"] for m in members}, axis=1, sort=True)
    dy = pd.concat({m: split[m]["daytime"] for m in members}, axis=1, sort=True)
    mask = on.notna() & dy.notna()
    count = mask.sum(axis=1)
    need = min(2, len(members))
    keep = count >= need
    out = pd.DataFrame({
        "overnight": on.where(mask).mean(axis=1),
        "daytime": dy.where(mask).mean(axis=1),
    })[keep]
    out["full"] = (1 + out["overnight"]) * (1 + out["daytime"]) - 1
    return out.dropna()


# ================================================================ strategies

def trend_positions(sr, days):
    """
    signal_t = 1 if the price index closes above its N-day average on day t.
    Trades at the next open, so:
      daytime exposure on day t   = signal_{t-1}
      overnight exposure on day t = signal_{t-2}  (the position held at the prior close)
    """
    index = (1 + sr["full"]).cumprod()
    ma = index.rolling(days, min_periods=days).mean()
    signal = (index > ma).astype(float).where(ma.notna(), 0.0)
    pos_day = signal.shift(1).fillna(0.0)
    pos_night = signal.shift(2).fillna(0.0)
    return pos_night, pos_day


def strategy_returns(sr, args):
    cost = args.cost_bps / 1e4
    cash_daily = (1 + args.cash_yield) ** (1 / TRADING_DAYS) - 1

    overnight = (1 - cost) ** 2 * (1 + sr["overnight"]) - 1

    pos_night, pos_day = trend_positions(sr, args.trend_days)
    trades = pos_day.diff().abs().fillna(pos_day.iloc[0] if len(pos_day) else 0)
    night_leg = 1 + sr["overnight"] * pos_night
    day_leg = 1 + sr["daytime"] * pos_day + cash_daily * (1 - pos_day)
    trend = night_leg * day_leg * (1 - cost) ** trades - 1

    strat = pd.DataFrame({
        "Buy & hold": sr["full"],
        "Trend": trend,
        "Overnight": overnight,
    })
    return strat, pos_day


# ================================================================ metrics

def metrics(r):
    if r.empty:
        return {"Growth of $1": float("nan"), "CAGR": float("nan"), "Volatility": float("nan"),
                "Sharpe": float("nan"), "Max drawdown": float("nan")}
    eq = (1 + r).cumprod()
    years = len(r) / TRADING_DAYS
    end_value = eq.iloc[-1]
    sd = r.std()
    return {
        "Growth of $1": end_value,
        "CAGR": end_value ** (1 / years) - 1 if years > 0 and end_value > 0 else float("nan"),
        "Volatility": sd * math.sqrt(TRADING_DAYS),
        "Sharpe": r.mean() / sd * math.sqrt(TRADING_DAYS) if sd > 0 else float("nan"),
        "Max drawdown": (eq / eq.cummax() - 1).min(),
    }


def after_tax_yearly(r, st_tax):
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


def after_tax_trend(r, pos_day, st_tax, lt_tax):
    """Tax each round trip at exit; long-term if held 365+ calendar days."""
    wealth, carry = 1.0, 0.0
    basis, entry_date, prev = None, None, 0.0

    def realize(gain, held_days):
        nonlocal carry
        rate = lt_tax if held_days >= 365 else st_tax
        taxable = gain + carry
        if taxable > 0:
            carry = 0.0
            return taxable * rate
        carry = taxable
        return 0.0

    for d, ret, p in zip(r.index, r.values, pos_day.values):
        if p > 0 and prev == 0:
            basis, entry_date = wealth, d
        wealth *= 1 + ret
        if p == 0 and prev > 0 and basis is not None:
            wealth -= realize(wealth - basis, (d - entry_date).days)
            basis = None
        prev = p
    if basis is not None:  # still holding at the end: tax as if sold
        wealth -= realize(wealth - basis, (r.index[-1] - entry_date).days)
    return wealth


def break_even_bps(sr):
    n = len(sr)
    night = (1 + sr["overnight"]).prod()
    hold = (1 + sr["full"]).prod()
    if n == 0 or night <= hold:
        return 0.0
    return (1 - (hold / night) ** (1 / (2 * n))) * 1e4


# ================================================================ output helpers

def pct(x, digits=1):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.{digits}f}%"


def money(x):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"${x:,.2f}"


def section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# ================================================================ analysis

def analyze(name, sr, args):
    strat, pos_day = strategy_returns(sr, args)
    m = {k: metrics(strat[k]) for k in strat.columns}
    tax = {
        "Buy & hold": after_tax_at_end(strat["Buy & hold"], args.lt_tax),
        "Trend": after_tax_trend(strat["Trend"], pos_day, args.st_tax, args.lt_tax),
        "Overnight": after_tax_yearly(strat["Overnight"], args.st_tax),
    }
    entries = int(((pos_day > 0) & (pos_day.shift(1).fillna(0) == 0)).sum())
    recent = {}
    for label, days in [("1y", TRADING_DAYS), ("3y", 3 * TRADING_DAYS)]:
        if len(strat) >= days:
            recent[label] = {k: (1 + strat[k].iloc[-days:]).prod() - 1 for k in strat.columns}

    g = sr.groupby(sr.index.year)
    trend_by_year = strat["Trend"].groupby(strat.index.year).apply(lambda x: (1 + x).prod() - 1)
    yearly = pd.DataFrame({
        "buy & hold": g["full"].apply(lambda x: (1 + x).prod() - 1),
        "trend": trend_by_year,
        "overnight only": g["overnight"].apply(lambda x: (1 + x).prod() - 1),
        "daytime only": g["daytime"].apply(lambda x: (1 + x).prod() - 1),
    })

    return {
        "name": name, "sr": sr, "strat": strat, "pos_day": pos_day,
        "metrics": m, "tax": tax, "entries": entries, "recent": recent,
        "yearly": yearly, "in_market": pos_day.mean(),
        "break_even": break_even_bps(sr),
        "day_avg_bps": sr["daytime"].mean() * 1e4,
        "worst_nights": sr["overnight"].nsmallest(10),
    }


def summary_row(res, status=""):
    m, t, sr = res["metrics"], res["tax"], res["sr"]
    one = res["recent"].get("1y", {})
    return {
        "name": res["name"],
        "status": status,
        "from": sr.index[0].date(),
        "B&H CAGR": m["Buy & hold"]["CAGR"],
        "B&H maxDD": m["Buy & hold"]["Max drawdown"],
        "Trend CAGR": m["Trend"]["CAGR"],
        "Trend maxDD": m["Trend"]["Max drawdown"],
        "In mkt": res["in_market"],
        "Night CAGR": m["Overnight"]["CAGR"],
        "B&H after tax": t["Buy & hold"],
        "Trend after tax": t["Trend"],
        "Night after tax": t["Overnight"],
        "1y B&H": one.get("Buy & hold", float("nan")),
        "1y Trend": one.get("Trend", float("nan")),
        "Day avg bps": res["day_avg_bps"],
    }


def print_summary(rows, title):
    if not rows:
        return
    df = pd.DataFrame(rows)
    fmt = df.copy()
    for c in ["B&H CAGR", "B&H maxDD", "Trend CAGR", "Trend maxDD", "In mkt", "Night CAGR", "1y B&H", "1y Trend"]:
        fmt[c] = df[c].map(pct)
    for c in ["B&H after tax", "Trend after tax", "Night after tax"]:
        fmt[c] = df[c].map(money)
    fmt["Day avg bps"] = df["Day avg bps"].map(lambda v: f"{v:+.1f}")
    if (df["status"] == "").all():
        fmt = fmt.drop(columns="status")
    section(title)
    print(fmt.to_string(index=False))


def print_detail(res, members_note="", args=None):
    sr = res["sr"]
    section(f"{res['name']}   {sr.index[0].date()} to {sr.index[-1].date()}   ({len(sr)} trading days)")
    if members_note:
        print(members_note)
    table = pd.DataFrame(res["metrics"]).T
    table["After-tax $1"] = pd.Series(res["tax"])
    fmt = table.copy()
    fmt["Growth of $1"] = table["Growth of $1"].map(money)
    fmt["After-tax $1"] = table["After-tax $1"].map(money)
    for c in ["CAGR", "Volatility", "Max drawdown"]:
        fmt[c] = table[c].map(pct)
    fmt["Sharpe"] = table["Sharpe"].map(lambda v: "—" if math.isnan(v) else f"{v:.2f}")
    print(fmt.to_string())

    print(f"\nTrend: in the market {pct(res['in_market'], 0)} of days, {res['entries']} entries "
          f"({args.trend_days}-day average, cash at {pct(args.cash_yield)} a year)")
    be = res["break_even"]
    if be > 0:
        print(f"Overnight break-even cost: {be:.1f} bps per trade (above this, buy & hold wins pre-tax)")
    else:
        print("Overnight break-even cost: none. Overnight-only lost to buy & hold even with zero costs.")
    print(f"Day avg: {res['day_avg_bps']:+.1f} bps open-to-close "
          f"({'buying at the close has been cheaper' if res['day_avg_bps'] < 0 else 'buying at the open has been cheaper'})")
    for label, vals in res["recent"].items():
        print(f"Last {label}: " + ", ".join(f"{k.lower()} {pct(v)}" for k, v in vals.items()))

    print("\nWorst 10 overnight gaps:")
    for d, v in res["worst_nights"].items():
        print(f"  {d.date()}  {pct(v)}")

    print("\nYear by year (strategies after costs; overnight/daytime splits before costs):")
    print(res["yearly"].apply(lambda col: col.map(pct)).to_string())


def plot(results, out_dir, trend_days):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("\n(matplotlib not installed, skipping chart)")
        return None
    if not results:
        return None
    cols = 2
    rows = math.ceil(len(results) / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(12, 3.6 * rows), squeeze=False)
    colors = {"Buy & hold": "#3d3d3d", "Trend": "#1a7f5a", "Overnight": "#2563c9"}
    for ax, res in zip(axes.flat, results):
        strat, pos = res["strat"], res["pos_day"]
        for col in strat.columns:
            ax.plot((1 + strat[col]).cumprod(), label=col, color=colors[col], linewidth=1.2)
        ax.set_yscale("log")
        out = pos == 0
        ax.fill_between(pos.index, 0, 1, where=out, transform=ax.get_xaxis_transform(),
                        color="#999999", alpha=0.12, linewidth=0)
        ax.set_title(res["name"], fontsize=10)
        ax.grid(alpha=0.3)
        ax.axhline(1, color="#999999", linewidth=0.8)
        loc = mdates.AutoDateLocator(minticks=3, maxticks=8)
        ax.xaxis.set_major_locator(loc)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
    for ax in list(axes.flat)[len(results):]:
        ax.axis("off")
    axes.flat[0].legend(loc="upper left", fontsize=8)
    fig.suptitle(f"Growth of $1, log scale, after trading costs, before tax. "
                 f"Grey bands: trend strategy in cash ({trend_days}-day average)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    path = Path(out_dir) / "infra_chart.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


# ================================================================ main

def main():
    here = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description="AI-infrastructure backtest with an ethics screen (paper only).")
    p.add_argument("--universe", default=str(here / "universe.csv"))
    p.add_argument("--only-approved", action="store_true")
    p.add_argument("--start", default="2010-01-01")
    p.add_argument("--end", default=str(date.today()))
    p.add_argument("--trend-days", type=int, default=200)
    p.add_argument("--cash-yield", type=float, default=0.03)
    p.add_argument("--cost-bps", type=float, default=2.0)
    p.add_argument("--st-tax", type=float, default=0.35)
    p.add_argument("--lt-tax", type=float, default=0.20)
    p.add_argument("--detail-tickers", action="store_true")
    p.add_argument("--csv-dir", default=None)
    p.add_argument("--out", default="infra_results")
    args = p.parse_args()

    universe = load_universe(args.universe)
    excluded = universe[universe["status"] == "excluded"]
    active = universe[universe["status"] != "excluded"]
    if args.only_approved:
        active = active[active["status"] == "approved"]
    if active.empty:
        sys.exit("No stocks left after the ethics screen. Mark some rows approved, grey or review.")

    section("Ethics screen")
    counts = universe["status"].value_counts()
    print("  " + ", ".join(f"{s}: {counts.get(s, 0)}" for s in STATUSES))
    if not excluded.empty:
        print(f"  Excluded, not loaded: {', '.join(excluded['ticker'])}")
    grey = active[active["status"] == "grey"]
    if not grey.empty:
        print(f"  Grey, case by case: {', '.join(grey['ticker'])}")
    review = active[active["status"] == "review"]
    if not review.empty:
        print(f"  Not yet evaluated: {', '.join(review['ticker'])}")

    tickers = list(active["ticker"]) + [b for b in BENCHMARKS if b not in set(active["ticker"])]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nLoading prices for {len(tickers)} tickers ...")
    prices = (load_from_csv(tickers, args.csv_dir, args.start, args.end) if args.csv_dir
              else load_from_yahoo(tickers, args.start, args.end))
    split = {t: split_returns(df) for t, df in prices.items() if len(df) > args.trend_days + 30}
    short = [t for t in prices if t not in split]
    if short:
        print(f"  Too little history to test (need {args.trend_days + 30}+ days): {', '.join(short)}")
    if not split:
        sys.exit("No usable price data.")

    status_of = dict(zip(active["ticker"], active["status"]))

    # Layer baskets
    basket_results, basket_rows = [], []
    for layer, grp in active.groupby("layer", sort=False):
        members = [t for t in grp["ticker"] if t in split]
        sr = make_basket(split, members)
        if sr is None or len(sr) <= args.trend_days + 30:
            continue
        res = analyze(f"{layer} ({'+'.join(members)})", sr, args)
        res["members_note"] = ("Members and when each starts: " +
                               ", ".join(f"{m} {split[m].index[0].year}" for m in members))
        basket_results.append(res)
        basket_rows.append(summary_row(res))

    bench_results = [analyze(b, split[b], args) for b in BENCHMARKS if b in split]
    bench_rows = [summary_row(r) for r in bench_results]

    ticker_results = [analyze(t, split[t], args) for t in active["ticker"] if t in split]
    ticker_rows = [summary_row(r, status_of.get(r["name"], "")) for r in ticker_results]

    print_summary(basket_rows + bench_rows, "SUMMARY BY LAYER (equal-weight baskets) vs benchmarks")
    print_summary(ticker_rows, "SUMMARY BY STOCK")
    print("\nAfter-tax columns: what $1 became after your tax rates. In mkt: share of days the trend")
    print("strategy was invested. Day avg: open-to-close move; negative favors buying at the close.")

    for res in basket_results:
        print_detail(res, res.get("members_note", ""), args)
    for res in bench_results:
        print_detail(res, "", args)
    if args.detail_tickers:
        for res in ticker_results:
            print_detail(res, f"Ethics status: {status_of.get(res['name'], '')}", args)

    pd.DataFrame(basket_rows + bench_rows + ticker_rows).to_csv(out_dir / "summary.csv", index=False)
    yearly = []
    for res in basket_results + bench_results + ticker_results:
        y = res["yearly"].copy()
        y.insert(0, "name", res["name"])
        yearly.append(y)
    pd.concat(yearly).to_csv(out_dir / "yearly.csv", index_label="year")
    chart = plot(basket_results + bench_results, out_dir, args.trend_days)

    section("Saved")
    for f in ["summary.csv", "yearly.csv"]:
        print(f"  {out_dir / f}")
    if chart:
        print(f"  {chart}")
    print(f"  Ethics list: {args.universe}")
    print("\nPaper results only. Past patterns don't guarantee future returns.")


if __name__ == "__main__":
    main()