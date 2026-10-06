# TODO

Ordered. Do the first section before publishing.

## 1. Fix before the first commit
- [ ] **Fix `pyproject.toml`.** The `[build-system]` block with setuptools will likely fail `uv sync`: there are two top-level modules and no package, so setuptools auto-discovery errors. Remove `[build-system]` and add `[tool.uv]` with `package = false`.
- [ ] **Fix the README offline note.** It says `uv sync --frozen` creates `uv.lock`. It doesn't; `--frozen` needs an existing lock. Use `uv lock`, then commit `uv.lock`.
- [ ] **Pick one dependency source.** Drop `requirements.txt` (duplicates `pyproject.toml`) or keep it deliberately.
- [ ] **Update the script docstrings and error messages** to match uv. Both `.py` files still say `python3 -m venv ~/overnight-env` / `pip install ...` (docstring SETUP/RUN blocks, and the `sys.exit("yfinance isn't installed...")` lines).
- [ ] **Add a LICENSE** (e.g. MIT). A public repo without one is "all rights reserved".
- [ ] **Smoke test:** `uv run infra_backtest.py --help`, then a real run. Nothing has been executed yet, so the code is untested.
- [ ] **First commit and push** (`new-repo` skill can do it). Git email is `alex.lapinski@gmail.com` by the owner's choice.

## 2. Get real results
- [ ] Run `uv run infra_backtest.py` on real data; review `infra_results/summary.csv` and the chart.
- [ ] Sanity-check against known figures (e.g. SPY/QQQ CAGR) to confirm the return math.
- [ ] Decide whether `universe.csv` is committed (currently tracked) once it holds notes.

## 3. Ethics screen
- [ ] Research the 20 starting tickers; propose statuses with sourced `notes`; owner confirms.
- [ ] Re-run with `--only-approved`.

## 4. Code cleanup
- [ ] Small inconsistency: `overnight_backtest.py` `split_returns` filters only `Open > 0`; `infra_backtest.py` also checks `prev_close > 0`. Match them (or retire the old script).
- [ ] The two scripts duplicate `split_returns`, `metrics`, `after_tax_*`, `break_even_bps`, `pct`, `money`. Either move shared code into one module or delete `overnight_backtest.py` (README calls it superseded).
- [ ] Align the `--cash-yield` default (0.03) with the README example (0.04), or explain the difference.
- [ ] Add a small pytest smoke test using `--csv-dir` with synthetic data (the README says it was tested that way; the test isn't in the repo).

## 5. Research extensions (optional, from README)
- [ ] Walk-forward / out-of-sample check on the trend strategy (guards against overfitting the 200-day window).
- [ ] Survivorship-bias check: add names that fell out of favour.
- [ ] Momentum rotation across layers; bubble-crash signals; covered-call sim; IRA (tax-free) scenario.
- [ ] Keep paper-only: no broker code.
