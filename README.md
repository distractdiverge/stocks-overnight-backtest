# AI Infrastructure Market Research

Paper-only research tools for testing whether a few published market patterns could be used to grow personal savings modestly during the AI-stock boom and its possible collapse, inside a personal ethics screen.

**Nothing here connects to a broker, places trades, or gives financial advice.** The scripts download public daily prices, run backtests, and write reports. Any decision to invest real money is made by the owner, outside this codebase.

---

## For agents: read this first

- **Keep it paper-only.** Don't add broker APIs, order placement, API keys, or anything that moves money unless the owner explicitly asks. If asked, confirm first and keep that code separate from the research scripts.
- **Don't decide ethics statuses yourself.** `universe.csv` is the owner's judgment. You can research companies and *propose* a status with evidence in the `notes` column, but mark every proposal clearly and leave the final call to the owner.
- **Evaluate honestly.** The owner values rigor and direct evaluation. If a backtest shows an idea doesn't survive taxes, costs, or recent data, say so plainly. Don't oversell results, and treat short histories as weak evidence.
- **Look for things that break backtests:** look-ahead bias, survivorship bias (the default list is today's winners), overfitting parameters to the past, and patterns that faded after publication.
- **Cite sources** for any factual claim about a company or a market pattern.
- **Separate household money from experiments.** The owner's stated aim is to improve savings while isolating the household from failure. Proposals should respect a hard cap on capital at risk and predefined exit rules.

---

## Background

### The overnight effect

Bruce Knuteson (former MIT physics professor, former D.E. Shaw quant) documented that, across major stock indices since the 1990s, nearly all gains came **overnight** (previous close to next open), while **daytime** returns (open to close) were flat or negative. He argues large quant funds cause it by buying aggressively in the morning and selling in the afternoon. That explanation is disputed.

Elm Wealth (Haghani et al.) found the effect is **strongest in retail-heavy "attention" stocks** like Nvidia, Tesla, AMD and MicroStrategy. They attribute it to retail buying pushing up opening prices.

**Evidence against simply trading it:** NightShares launched ETFs in 2022 that held the market only overnight. NSPY fell about 7% while the S&P 500 rose about 22%, and both funds closed in August 2023. The practical drags are short-term taxes on every gain, gap risk from news that lands after hours, and the fact that buy-and-hold already captures the overnight return.

### Lower-turnover ideas carried forward

- **Close-timing purchases:** if daytime returns are negative on average, buying at the close (market-on-close order) is cheaper than buying at the open. This edge comes with no extra trades or taxes. The scripts report it as "Day avg".
- **Trend following** (Moskowitz, Ooi & Pedersen): hold while price is above its 200-day moving average and move to cash or T-bills when it falls below. It has low turnover and a built-in exit, which suits the "isolate from failure" goal. The cost is whipsaws.
- Other principles discussed but **not yet implemented**: momentum rotation (Jegadeesh & Titman), bubble-crash signals (Greenwood, Shleifer & You: sector run-ups plus rising volatility, accelerating gains, and heavy new stock issuance), covered calls (volatility risk premium), and avoiding lottery-like attention spikes. Published anomalies typically shrink about 50% after publication (McLean & Pontiff), so recent-period performance matters most.

### Why infrastructure

Most frontier AI labs are private, but the infrastructure behind them is publicly traded. Historical caution: in the dot-com bust, infrastructure builders fell hardest (Cisco fell more than 80%, and fiber carriers went bankrupt from overbuilding). Bubble exposure differs by layer:

| Layer | Examples | Bubble exposure |
|---|---|---|
| chips_memory | NVDA, AVGO, AMD, MU, TSM | Highest: orders can drop fast |
| chip_equipment | ASML, AMAT, LRCX | High: classic cyclicals |
| networking_optics | ANET, COHR, CIEN | High: closest parallel to the 2000 fiber bust |
| power_cooling | VRT, ETN, GEV | Moderate: grid upgrades needed regardless |
| utilities_nuclear | CEG, VST | Lower business risk, but prices may assume AI demand |
| data_centers | EQIX, DLR | Moderate: long leases, tenant risk |
| clean_power | NEE, FSLR | Added as the closest fit to the owner's positive criterion |

The examples come from model training data as of mid-2026 and have not been verified against current news.

---

## Ethics screen

The owner's rules:

1. **Exclude** anything that feeds the American war machine.
2. **Exclude** anything that supports Trump/MAGA or Israel.
3. **Grey area:** companies with indirect ties (e.g., Nvidia) are evaluated case by case.
4. **Prefer** companies contributing to a post-scarcity, Star Trek-style future.

Ethical framing: buying existing shares on the open market sends money to the seller, not the company. Companies raise capital only through new issuance (IPOs, secondary offerings). So the intent is to trade existing shares and avoid new issues.

### `universe.csv`

The script creates `universe.csv` on first run. Columns: `ticker, name, layer, status, notes`.

| status | Meaning |
|---|---|
| `approved` | Passes the screen |
| `grey` | Case by case; tested and flagged in output |
| `review` | Not yet evaluated (default for every row) |
| `excluded` | Never loaded or tested |

The `layer` column decides basket membership. Rows can be added or removed freely.

Where to check a company:
- Annual report (10-K / 20-F): segment and customer disclosures for defense or government revenue
- [USAspending.gov](https://www.usaspending.gov): federal contracts, filtered to the Department of Defense
- [OpenSecrets.org](https://www.opensecrets.org): corporate PAC and executive political giving
- [AFSC Investigate](https://investigate.afsc.org): companies tied to Israeli occupation, prisons, and border militarization

Record findings and sources in `notes`.

---

## Files

| File | Purpose |
|---|---|
| `README.md` | This file: context and instructions for humans and agents |
| `infra_backtest.py` | **Main tool.** Layer baskets plus individual stocks, ethics screen, and three strategies (buy & hold, 200-day trend, overnight-only) with after-tax results |
| `overnight_backtest.py` | Earlier, simpler tool: overnight vs. daytime split for a fixed list of AI stocks. Superseded by `infra_backtest.py` but kept for reference |
| `requirements.txt` | Python package dependencies (yfinance, pandas, numpy, matplotlib) |
| `universe.csv` | **Generated on first run.** Owner's ethics-screened stock list (created by `infra_backtest.py`; edit and re-run to change statuses) |
| `infra_results/` | **Generated on run.** Output: `summary.csv`, `yearly.csv`, `infra_chart.png` |
| `overnight_results/` | **Generated on run.** Output from `overnight_backtest.py` |

---

## Setup and running

Requires Python 3.9+. Install [uv](https://docs.astral.sh/uv/):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then run:

```bash
uv run --with yfinance --with pandas --with matplotlib infra_backtest.py --st-tax 0.35 --lt-tax 0.20 --cash-yield 0.04
```

Or, to install dependencies once and reuse:

```bash
uv sync
uv run infra_backtest.py --st-tax 0.35 --lt-tax 0.20 --cash-yield 0.04
```

| Option | Default | Meaning |
|---|---|---|
| `--universe` | `universe.csv` next to the script | Ethics-screened stock list |
| `--only-approved` | off | Test only `approved` rows |
| `--start` / `--end` | 2010-01-01 / today | Date range |
| `--trend-days` | 200 | Moving-average length for the trend exit |
| `--cash-yield` | 0.03 | Annual yield while in cash; set to the current 3-month T-bill yield |
| `--cost-bps` | 2 | Cost per trade in basis points |
| `--st-tax` / `--lt-tax` | 0.35 / 0.20 | Short- and long-term tax rates, federal plus state |
| `--detail-tickers` | off | Full report for every stock, not just baskets |
| `--csv-dir` | none | Read `TICKER.csv` files (Date, Open, Close) instead of downloading |
| `--out` | `infra_results` | Output folder |

`--csv-dir` is useful offline or for testing with synthetic data.

For offline use, run `uv sync --frozen` once to lock dependency versions (creates `uv.lock`), then `uv run` works without network access.

---

## How the numbers are computed

- **Return split:** overnight = open / previous close − 1; daytime = close / open − 1. Prices are split- and dividend-adjusted (Yahoo `auto_adjust`), so dividends land in the overnight leg and flatter it slightly.
- **Baskets:** equal-weight, rebalanced daily at no cost, over whichever members traded that day (at least two when possible). Members that listed later join when their history starts.
- **Trend strategy:** the signal is computed at day *t*'s close and traded at day *t+1*'s open, so there is no look-ahead. In cash it earns `--cash-yield`. Costs are charged on each entry and exit.
- **Overnight strategy:** buy at the close, sell at the next open, with cost charged twice per day.
- **Taxes (simplified, for comparison only):**
  - Buy & hold: taxed once at the end at the long-term rate.
  - Trend: each round trip taxed at exit, long-term if held 365+ days, with losses carried forward.
  - Overnight: net gains taxed yearly at the short-term rate.
  - No wash-sale rules. Open positions are taxed as if sold at the end.
- **Break-even cost:** the per-trade cost at which overnight-only would exactly match buy & hold before tax.
- **Day avg:** mean open-to-close move in basis points. Negative means buying at the close has been cheaper.

### Known limitations

- **Survivorship bias:** the default list is today's prominent companies, which inflates historical results.
- **Short histories:** GEV (2024), CEG (2022) and VRT (2020) give little data.
- Yahoo's "Open" approximates the official opening auction price.
- Tested only on synthetic data so far. **Real-data results have not yet been reviewed.**

---

## Status and next steps

- [x] Overnight vs. daytime backtester (`overnight_backtest.py`)
- [x] Infrastructure layers, ethics screen, trend exit, after-tax comparison (`infra_backtest.py`)
- [ ] Run on real data on the owner's Mac and review the results
- [ ] Research the 20 starting companies against the ethics rules and propose statuses with sourced notes, for the owner to confirm
- [ ] Possible additions: bubble-crash signals (run-up, volatility, issuance), momentum rotation across layers, covered-call simulation, IRA (tax-free) scenario

Sources: Knuteson, *Information, Impact, Ignorance, Illegality, Investing, and Inequality* (arXiv 1612.06855); Elm Wealth, "Night Shift" (2025); Advisor Perspectives, "We Still Need to Find Out Why Stock Gains Come at Night" (2025); WealthManagement / Bloomberg on the NightShares closures (July 2023).