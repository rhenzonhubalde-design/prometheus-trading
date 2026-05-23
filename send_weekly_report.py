"""
Per-account weekly Telegram report.

Trigger: Saturday morning SGT (after Fri US close).
Window:  Mon 00:00 → Sun 23:59 SGT of the just-completed US trading week.
Sends:   one Telegram message per account (A and B), each with:
          - trades opened / closed this week
          - realized PnL (USD-weighted, in account base currency)
          - win rate (week-bounded)
          - best / worst trade of the week
          - end-of-week open positions snapshot with unrealized %

Cron (production VPS):
    # Sat 08:00 SGT — fire weekly per-account report
    0 8 * * 6  cd ~/prometheus && /usr/bin/python3 send_weekly_report.py

Manual: `python3 send_weekly_report.py` (uses current SGT time to pick the week).
"""
import sys, os, math, json

sys.path.insert(0, os.path.expanduser('~/prometheus'))
sys.path.insert(0, os.path.expanduser('~/prometheus/phase3'))

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.expanduser('~/prometheus/.env'))

import reporting
import telegram_alerts as tg

BASE_DIR = os.path.expanduser('~/prometheus')


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def fetch_prices_and_account_value(data_dir, ib_port, label):
    """
    Look up the open positions and fetch live prices + account NetLiq in
    the account's base currency. Falls back to entry prices if IBKR is
    unreachable, so the report still goes out with zero unrealized rather
    than failing silently.
    """
    open_p = load_json(os.path.join(data_dir, 'open_positions.json'), [])
    prices = {p.get('ticker'): None for p in open_p if p.get('ticker')}
    account_value, currency = 100_000.0, 'USD'

    try:
        from ib_insync import IB, Stock
        ib = IB()
        ib.connect('127.0.0.1', ib_port, clientId=98, timeout=10)
        ib.reqMarketDataType(4)

        managed    = ib.managedAccounts()
        my_account = managed[0] if managed else None
        for av in ib.accountValues():
            if my_account and av.account != my_account:
                continue
            if av.tag == 'NetLiquidation' and av.currency and av.currency != 'BASE':
                currency      = av.currency
                account_value = float(av.value)

        for ticker in list(prices.keys()):
            try:
                contract = Stock(ticker, 'SMART', 'USD')
                ib.qualifyContracts(contract)
                td = ib.reqMktData(contract, '', False, False)
                ib.sleep(2)
                for attr in ['last', 'close', 'bid']:
                    v = getattr(td, attr, None)
                    if v and not math.isnan(v) and v > 0:
                        prices[ticker] = float(v)
                        break
            except Exception:
                pass

        ib.disconnect()
    except Exception as e:
        print(f"  [{label}] IBKR fetch failed: {e}")

    return account_value, currency, prices, open_p


def run_for_account(data_dir, ib_port, label):
    closed = load_json(os.path.join(data_dir, 'closed_positions.json'), [])
    account_value, currency, prices, open_p = fetch_prices_and_account_value(
        data_dir, ib_port, label
    )
    stats = reporting.compute_weekly_stats(
        open_positions=open_p,
        closed_positions=closed,
        current_prices=prices,
        account_value=account_value,
        account_label=label,
        currency=currency,
    )
    print(f"  [{label}] Window {stats['week_start']} → {stats['week_end']}  "
          f"| opened {stats['opened_count']} | closed {stats['closed_count']}  "
          f"| realized {currency} {stats['realized_pnl_usd']:+.2f}")
    tg.send_weekly_account_report(stats)


if __name__ == '__main__':
    for acct, port, label in [
        ('account_a', 4002, 'A — BASELINE'),
        ('account_b', 4003, 'B — LEARNING'),
    ]:
        try:
            run_for_account(os.path.join(BASE_DIR, acct, 'data'), port, label)
        except Exception as e:
            print(f"[{label}] Weekly report failed: {e}")
            import traceback; traceback.print_exc()
    print("Weekly per-account reports sent.")
