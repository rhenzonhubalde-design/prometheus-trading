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

    # ── Step 5: Weekly A/B comparison (if journal ran) ─────────
    stats_a = calc_stats(os.path.join(ACCT_A_DIR, 'data'))
    stats_b = calc_stats(os.path.join(ACCT_B_DIR, 'data'))

    # Send weekly A/B summary on Mondays or if first run
    if datetime.now().weekday() == 0 or (stats_a['closed'] > 0 and stats_b['closed'] > 0):
        try:
            tg.send_ab_weekly_summary(stats_a, stats_b)
        except Exception as e:
            print(f"  A/B summary failed: {e}")

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
