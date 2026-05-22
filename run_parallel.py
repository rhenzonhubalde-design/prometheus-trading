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

def get_portfolio_snapshot(data_dir, ib_port, label):
    """Fetch realized + unrealized P&L and risk exposure for an account."""
    import json, math
    from ib_insync import IB

    closed = load_json(os.path.join(data_dir, 'closed_positions.json'), [])
    open_p = load_json(os.path.join(data_dir, 'open_positions.json'), [])

    # Realized P&L from closed trades
    realized_pnl   = sum(float(p.get('pnl_pct', 0)) for p in closed)
    wins           = [p for p in closed if float(p.get('pnl_pct', 0)) > 0]
    losses         = [p for p in closed if float(p.get('pnl_pct', 0)) < 0]
    win_rate       = round(len(wins) / len(closed) * 100, 1) if closed else 0

    # Unrealized P&L from IBKR account summary (authoritative — not the sum of position-level PNLs).
    # Reported in the account's base currency (e.g. SGD) to match what's shown in the IBKR account screen.
    unrealized_pnl = 0.0
    account_value  = 100_000
    currency       = 'USD'
    positions_pnl  = []
    try:
        ib = IB()
        ib.connect('127.0.0.1', ib_port, clientId=97)
        for item in ib.portfolio():
            pct = ((item.unrealizedPNL or 0) / (item.averageCost * item.position) * 100) if item.position else 0
            positions_pnl.append({
                'ticker': item.contract.symbol,
                'pnl_usd': round(item.unrealizedPNL or 0, 2),
                'pct': round(pct, 2),
                'market_value': round(item.marketValue or 0, 2),
            })
        # accountValues() can return rows for multiple accounts when a gateway has access
        # to more than one — filter to the account this gateway manages.
        managed = ib.managedAccounts()
        my_account = managed[0] if managed else None
        for av in ib.accountValues():
            if my_account and av.account != my_account:
                continue
            # Detect base currency from any non-BASE row on this account
            if av.tag == 'AccountReady' and av.currency and av.currency != 'BASE':
                pass  # informational only
            if av.tag == 'NetLiquidation':
                if av.currency != 'BASE':
                    currency = av.currency
                    account_value = float(av.value)
            elif av.tag == 'UnrealizedPnL' and av.currency == 'BASE':
                unrealized_pnl = float(av.value)
        ib.disconnect()
    except Exception as e:
        print(f"  Portfolio fetch failed ({label}): {e}")

    # Risk exposure
    total_deployed = sum(float(p.get('position_size_pct', 0)) for p in open_p)
    sectors = {}
    for p in open_p:
        s = p.get('sector', 'Unknown').split('(')[0].strip()
        sectors[s] = sectors.get(s, 0) + float(p.get('position_size_pct', 0))
    top_sector = max(sectors.items(), key=lambda x: x[1]) if sectors else ('None', 0)

    return {
        'label':          label,
        'account_value':  account_value,
        'currency':       currency,
        'realized_pnl':   round(realized_pnl, 2),
        'unrealized_pnl': round(unrealized_pnl, 2),
        'total_pnl':      round(realized_pnl + (unrealized_pnl / account_value * 100), 2),
        'win_rate':        win_rate,
        'closed_trades':  len(closed),
        'open_trades':    len(open_p),
        'deployed_pct':   round(total_deployed, 1),
        'top_sector':     top_sector,
        'positions_pnl':  positions_pnl,
    }




def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def calc_stats(data_dir):
    """Calculate quick stats for a given account's data directory"""
    closed = load_json(os.path.join(data_dir, 'closed_positions.json'), [])
    open_p = load_json(os.path.join(data_dir, 'open_positions.json'), [])
    if not closed:
        return {'total_trades': len(open_p), 'closed': 0,
                'overall_win_rate': 0, 'overall_avg_pnl': 0}
    wins    = [p for p in closed if float(p.get('pnl_pct', 0)) > 0]
    avg_pnl = sum(float(p.get('pnl_pct', 0)) for p in closed) / len(closed)
    return {
        'total_trades':      len(open_p) + len(closed),
        'closed':            len(closed),
        'open':              len(open_p),
        'overall_win_rate':  round(len(wins) / len(closed) * 100, 1),
        'overall_avg_pnl':   round(avg_pnl, 2),
    }


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

    # ── Step 4: Combined daily summary ────────────────────────
    open_a   = result_a.get('monitor', {}).get('still_open', [])
    open_b   = result_b.get('monitor', {}).get('still_open', [])
    closed_a = result_a.get('monitor', {}).get('closed', [])
    closed_b = result_b.get('monitor', {}).get('closed', [])

    tg.send_daily_summary(
        open_positions=open_a + open_b,
        theses_count=result_a.get('theses_count', 0) + result_b.get('theses_count', 0),
        approved_count=result_a.get('approved', 0) + result_b.get('approved', 0),
        closed_today=closed_a + closed_b,
    )
    # Portfolio P&L snapshot
    try:
        snap_a = get_portfolio_snapshot(
            os.path.join(ACCT_A_DIR, 'data'), 4002, 'A — BASELINE')
        snap_b = get_portfolio_snapshot(
            os.path.join(ACCT_B_DIR, 'data'), 4003, 'B — LEARNING')
        tg.send_portfolio_snapshot(snap_a, snap_b)
    except Exception as e:
        print(f"  Portfolio snapshot failed: {e}")
    # ── Step 5: Weekly A/B comparison (if journal ran) ─────────
    stats_a = calc_stats(os.path.join(ACCT_A_DIR, 'data'))
    stats_b = calc_stats(os.path.join(ACCT_B_DIR, 'data'))


    elapsed = (datetime.now() - start).seconds
    print(f"\n{'=' * 60}")
    print(f"  PARALLEL PIPELINE COMPLETE — {elapsed}s")
    print(f"  Account A: {result_a.get('approved',0)} trades | {len(open_a)} open")
    print(f"  Account B: {result_b.get('approved',0)} trades | {len(open_b)} open")
    print(f"\n  A/B Scorecard:")
    print(f"  Account A win rate: {stats_a['overall_win_rate']}% over {stats_a['closed']} closed")
    print(f"  Account B win rate: {stats_b['overall_win_rate']}% over {stats_b['closed']} closed")
    print(f"{'=' * 60}\n")


if __name__ == '__main__':
    run_all()
