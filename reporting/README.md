# Reporting

Standalone daily and weekly Telegram reports for the Prometheus paper trading
system. Decoupled from the trading strategy — does not import from `phase1/2/3`
or `run_parallel.py`, and is not imported by them.

## Source of truth

| Data | File / Source |
|---|---|
| Open positions | `account_a/data/open_positions.json`, `account_b/data/open_positions.json` |
| Closed positions | `account_a/data/closed_positions.json`, `account_b/data/closed_positions.json` |
| Live prices | IBKR `reqMktData` per ticker → yfinance fallback for gaps |
| Account value (NetLiq) | IBKR `accountValues()` row where `tag=NetLiquidation`, `currency != BASE`, account matches gateway's managed account |
| Account currency | Same IBKR row — whichever currency the gateway reports |

These JSON files are written by the trading strategy (monitor + execution).
Reporting reads them only — never writes.

## Entry points

```bash
python3 -m reporting.daily      # per-account daily snapshot
python3 -m reporting.weekly     # per-account weekly summary
```

## Cron (production VPS)

```
# Daily — ~30min after run_parallel.py completes
30 21 * * 1-5  cd ~/prometheus && /usr/bin/python3 -m reporting.daily

# Weekly — Sat 08:00 SGT, after Fri US close
0 8 * * 6      cd ~/prometheus && /usr/bin/python3 -m reporting.weekly
```

## Daily message contains

- Number of open trades
- Current risk exposure: `$ at risk` budgeted (sum of `risk_per_share × qty`,
  or full `entry_size_usd` for positions without a parseable stop) AND live
  (`(current - stop) × qty` for longs, mirrored for shorts).
- Unrealized PnL in account base currency, expressed two ways:
  - **`% of account`** — total unrealized $ ÷ NetLiquidation
  - **`% avg position`** — size-weighted average of per-position unrealized %

## Weekly message contains

- Week window: most recently completed Mon→Sun SGT
- Activity: trades opened, trades closed (wins/losses split)
- Realized PnL of the week — **USD-weighted** (not sum of pnl_pct)
- Best and worst trade of the week with exit reason
- End-of-week open positions snapshot with current unrealized %

## Files

```
reporting/
├── __init__.py
├── stats.py       # Pure functions: week bounds, daily stats, weekly stats
├── messages.py    # Pure formatters: stats dict → Telegram message string
├── telegram.py    # Self-contained Telegram client (duplicates send() from phase3)
├── ibkr.py        # Live price + NetLiq fetcher (read-only; never places orders)
├── data.py        # JSON loaders + ACCOUNTS list
├── daily.py       # Entry point — wires everything for daily
├── weekly.py      # Entry point — wires everything for weekly
└── tests/
    ├── __init__.py
    └── test_stats.py   # 50 unit tests
```

## Running tests

```bash
python3 -m unittest reporting.tests.test_stats -v
```
