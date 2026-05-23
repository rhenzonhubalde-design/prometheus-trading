# Report

Standalone daily/weekly Telegram reports + FastAPI dashboard for the Prometheus
Account A paper trading system. Decoupled from `trading/` — the trading code
doesn't import `report/`, and `report/` doesn't import `trading/`. The only
contract is the on-disk JSON state in `data/account_a/` and the SQLite history
in `data/prometheus.db`.

## Source of truth

| Data | File / Source | Reader |
|---|---|---|
| Open positions (live) | `data/account_a/open_positions.json` | `report/positions_loader.py` |
| Closed positions (live) | `data/account_a/closed_positions.json` | `report/positions_loader.py` |
| Today's approvals / rejections | `data/account_a/{approved,rejected}_trades.json` | `report/positions_loader.py` |
| Closed trades (history) | `data/prometheus.db` → `closed_trades` table | `report/db.py` |
| Daily account snapshots | `data/prometheus.db` → `daily_snapshots` table | `report/db.py` |
| Trade events log | `data/prometheus.db` → `trade_events` table | `report/db.py` |
| Live prices | IBKR `reqMktData` → yfinance fallback | `report/ibkr.py` |
| Account value (NetLiq) | IBKR `accountValues()` row where `tag=NetLiquidation`, `currency != BASE` | `report/ibkr.py` |

Reports never write to position JSON files. The daily report writes one row to
`daily_snapshots` (idempotent upsert on `(snapshot_date, account)`).

## Entry points

```bash
python3 -m report.daily      # per-account daily snapshot + writes SQLite snapshot
python3 -m report.weekly     # per-account weekly summary (Mon→Sun SGT window)
```

## Cron (production VPS)

```cron
# Daily — ~30min after trading run completes
30 21 * * 1-5  cd ~/prometheus && /usr/bin/python3 -m report.daily   >> data/logs/daily.log  2>&1

# Weekly — Sat 08:00 SGT, after Fri US close
0 8 * * 6      cd ~/prometheus && /usr/bin/python3 -m report.weekly  >> data/logs/weekly.log 2>&1

# Plotus IG brief — every day (incl. weekends, for reflective posts)
15 5 * * *     cd ~/prometheus && /usr/bin/python3 -m report.plotus.daily  >> data/logs/plotus_daily.log  2>&1

# Plotus IG weekly brief — Sat 08:15 SGT, after weekly Telegram
15 8 * * 6     cd ~/prometheus && /usr/bin/python3 -m report.plotus.weekly >> data/logs/plotus_weekly.log 2>&1
```

## Plotus (Instagram) briefs

A separate output channel that emits a narrative + sanitized data drop to
Google Drive for the Hermes content system to pick up. Daily runs every day
(reflective posts on non-trading days); weekly runs Saturday after Fri close.

| | |
|---|---|
| **Drop folder** | `gdrive:AI Trading/Plotus/Briefs/{YYYY-MM-DD}/` |
| **brief.md** | 2-4 paragraph third-person narrative ("Plotus opened…"), tone varies by editorial angle |
| **data.json** | Sanitized payload — percentages only, no $ figures, no NetLiq, no entry prices |
| **Privacy** | `report/plotus/sanitizer.py` strips $-keys from the payload and refuses to ship `brief.md` with $-figures or NetLiq-style tokens in it |
| **Angles** | `winning` / `losing` / `retrospective` / `milestone` / `quiet` / `reflective` — picked from what actually happened that day or week |
| **Local mirror** | `data/plotus_briefs/{date}/` (gitignored) |

## Daily message contains

- Open trade count
- `$ at risk`: budgeted (sum of `risk_per_share × qty`, full `entry_size_usd` for
  unstopped positions) and live (`(current − stop) × qty`)
- Unrealized PnL: `% of account` (vs NetLiq) and `% avg position` (size-weighted)
- **Today's decisions**: approved theses + rejected with reason
- **Today's activity**: trades opened today, trades closed today with PnL

## Weekly message contains

- Window: Mon→Sun SGT of the most recently completed week
- Opened / closed counts (wins / losses split)
- Realized PnL (USD-weighted, in account base currency)
- Best / worst trade with exit reason
- End-of-week open positions snapshot with current unrealized %

## Files

```
report/
├── stats.py             pure stats (week bounds, daily/weekly math)
├── messages.py          pure formatters (stats → Telegram string)
├── telegram.py          self-contained Telegram client
├── ibkr.py              read-only price + NetLiq fetcher
├── positions_loader.py  JSON loaders + ACCOUNTS list
├── db.py                SQLite history layer (closed_trades, daily_snapshots, events, journal)
├── daily.py             python3 -m report.daily
├── weekly.py            python3 -m report.weekly
├── dashboard/           FastAPI live dashboard (reads SQLite + live IBKR)
├── plotus/              Plotus / Instagram brief pipeline (daily + weekly drops to Google Drive)
├── requirements.txt     pip install -r report/requirements.txt
└── tests/test_stats.py  50+ unit tests
```

## Running tests

```bash
python3 -m unittest report.tests.test_stats -v
```
