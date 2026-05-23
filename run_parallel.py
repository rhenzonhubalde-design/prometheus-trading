"""
Prometheus — Parallel Master Runner
Runs Account A (Baseline) and Account B (Learning) in parallel every weekday.
Research runs ONCE and is shared. Each account runs its own pipeline independently.
"""
import os
import sys
import json
from datetime import datetime

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
PHASE2_DIR = os.path.join(BASE_DIR, 'phase2')
ACCT_A_DIR = os.path.join(BASE_DIR, 'account_a')
ACCT_B_DIR = os.path.join(BASE_DIR, 'account_b')

sys.path.insert(0, os.path.join(BASE_DIR, 'phase3'))
sys.path.insert(0, PHASE2_DIR)

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.expanduser('~/prometheus/.env'))

def fetch_account_value_and_prices(data_dir, ib_port, account_label):
    """
    Fetch live prices for every open position and the account's NetLiquidation
    value in the account's BASE currency. Returns (account_value, currency,
    {ticker: current_price or None}).

    Currency handling: the IBKR account base currency is detected from any
    NetLiquidation row whose currency tag is not 'BASE' and matches the gateway's
    managed account. All $ amounts in the daily/weekly report use this currency.
    """
    import math
    from ib_insync import IB, Stock

    open_p = load_json(os.path.join(data_dir, 'open_positions.json'), [])
    prices = {p.get('ticker'): None for p in open_p if p.get('ticker')}
    account_value, currency = 100_000.0, 'USD'

    try:
        ib = IB()
        ib.connect('127.0.0.1', ib_port, clientId=97, timeout=10)
        ib.reqMarketDataType(4)   # delayed (free tier)

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
        print(f"  Price/account fetch failed ({account_label}): {e}")

    # yfinance fallback for tickers still missing
    missing = [t for t, v in prices.items() if v is None]
    if missing:
        try:
            import yfinance as yf
            for t in missing:
                try:
                    fi = yf.Ticker(t).fast_info
                    p_yf = getattr(fi, "last_price", None) or getattr(fi, "previous_close", None)
                    if p_yf and not math.isnan(float(p_yf)) and float(p_yf) > 0:
                        prices[t] = float(p_yf)
                except Exception:
                    pass
        except ImportError:
            pass

    return account_value, currency, prices




def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def run_all():
    import telegram_alerts as tg

    start = datetime.now()
    print("=" * 60)
    print(f"  PROMETHEUS PARALLEL A/B PIPELINE")
    print(f"  {start.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Account A: Baseline (port 4002)")
    print(f"  Account B: Learning (port 4003)")
    print("=" * 60)

    # ── Step 1: Research (runs ONCE, shared) ──────────────────
    print("\n[SHARED] Running research pipeline...")
    try:
        orig = os.getcwd()
        os.chdir(PHASE2_DIR)
        import run_research
        run_research.run_all()
        os.chdir(orig)
    except Exception as e:
        print(f"  Research failed: {e}")
        try: os.chdir(BASE_DIR)
        except: pass

    # ── Step 2: Account A (Baseline) ──────────────────────────
    print("\n[ACCOUNT A — BASELINE]")
    result_a = {}
    try:
        sys.path.insert(0, ACCT_A_DIR)
        import run_account_a
        result_a = run_account_a.run() or {}
    except Exception as e:
        print(f"  Account A failed: {e}")
        import traceback; traceback.print_exc()

    # ── Step 3: Account B (Learning) ──────────────────────────
    print("\n[ACCOUNT B — LEARNING]")
    result_b = {}
    try:
        sys.path.insert(0, ACCT_B_DIR)
        import run_account_b
        result_b = run_account_b.run() or {}
    except Exception as e:
        print(f"  Account B failed: {e}")
        import traceback; traceback.print_exc()

    # ── Step 4: Per-account daily reports ─────────────────────
    # Reads the source-of-truth files (open_positions.json) rather than relying
    # on the monitor's in-memory result, so a monitor failure can't blank the
    # daily report.
    import reporting

    for acct_dir, port, label in [
        (ACCT_A_DIR, 4002, 'A — BASELINE'),
        (ACCT_B_DIR, 4003, 'B — LEARNING'),
    ]:
        try:
            data_dir = os.path.join(acct_dir, 'data')
            open_p   = load_json(os.path.join(data_dir, 'open_positions.json'), [])
            acct_val, currency, prices = fetch_account_value_and_prices(data_dir, port, label)
            stats = reporting.compute_daily_stats(
                open_positions=open_p,
                current_prices=prices,
                account_value=acct_val,
                account_label=label,
                currency=currency,
            )
            tg.send_daily_account_report(stats)
        except Exception as e:
            print(f"  Daily report failed ({label}): {e}")
            import traceback; traceback.print_exc()

    elapsed = (datetime.now() - start).seconds
    open_a = load_json(os.path.join(ACCT_A_DIR, 'data', 'open_positions.json'), [])
    open_b = load_json(os.path.join(ACCT_B_DIR, 'data', 'open_positions.json'), [])
    print(f"\n{'=' * 60}")
    print(f"  PARALLEL PIPELINE COMPLETE — {elapsed}s")
    print(f"  Account A: {result_a.get('approved',0)} trades | {len(open_a)} open")
    print(f"  Account B: {result_b.get('approved',0)} trades | {len(open_b)} open")
    print(f"{'=' * 60}\n")


if __name__ == '__main__':
    run_all()
