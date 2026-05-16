"""
Prometheus Phase 3 — Master Orchestrator (Autonomous)
Full daily pipeline: Research -> Risk -> Execute -> Monitor -> Telegram summary
Everything runs autonomously. Telegram is the notification layer, not the control layer.
"""
import sys
import os
from datetime import datetime
 
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
 
PHASE2_DIR = os.path.expanduser('~/prometheus/phase2')
sys.path.insert(0, PHASE2_DIR)
 
 
def load_json(path, default):
    import json
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default
 
 
def run_all():
    import telegram_alerts as tg
 
    start = datetime.now()
    print("=" * 60)
    print(f"  PROMETHEUS FULL PIPELINE - {start.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
 
    # ── 1: Research ───────────────────────────────────────────
    print("\n[1/4] Running research pipeline...")
    try:
        orig_dir = os.getcwd()
        os.chdir(PHASE2_DIR)
        import run_research
        run_research.run_all()
        os.chdir(orig_dir)
    except Exception as e:
        print(f"  Research failed: {e}")
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
 
    # ── 2: Risk Manager ───────────────────────────────────────
    print("\n[2/4] Running Risk Manager...")
    risk_result = None
    try:
        import risk_manager
        risk_result = risk_manager.run()
    except Exception as e:
        print(f"  Risk Manager failed: {e}")
        tg.send(f"PROMETHEUS ERROR - Risk Manager failed:\n{e}")
 
    approved_count = len((risk_result or {}).get('approved', []))
    rejected_count = len((risk_result or {}).get('rejected', []))
    print(f"  Approved: {approved_count} | Rejected: {rejected_count}")
 
    # ── 3: Execution ──────────────────────────────────────────
    executed = []
    if approved_count > 0:
        print(f"\n[3/4] Executing {approved_count} approved trade(s) autonomously...")
        try:
            import execution_agent
            executed = execution_agent.run() or []
        except Exception as e:
            print(f"  Execution failed: {e}")
            tg.send(f"PROMETHEUS ERROR - Execution Agent failed:\n{e}")
    else:
        print("\n[3/4] No approved trades - skipping execution.")
 
    # ── 4: Monitor ────────────────────────────────────────────
    print("\n[4/4] Running Monitor Agent...")
    monitor_result = {'still_open': [], 'closed': []}
    try:
        import monitor_agent
        monitor_result = monitor_agent.run() or monitor_result
    except Exception as e:
        print(f"  Monitor failed: {e}")
        tg.send(f"PROMETHEUS ERROR - Monitor Agent failed:\n{e}")
 
    # ── Daily Summary Telegram ────────────────────────────────
    theses_data = load_json(
        os.path.join(PHASE2_DIR, 'data/trade_theses.json'), {}
    )
    tg.send_daily_summary(
        open_positions=monitor_result.get('still_open', []),
        theses_count=len(theses_data.get('theses', [])),
        approved_count=approved_count,
        closed_today=monitor_result.get('closed', [])
    )
 
    # ── Summary ───────────────────────────────────────────────
    elapsed = (datetime.now() - start).seconds
    print(f"\n{'=' * 60}")
    print(f"  PIPELINE COMPLETE - {elapsed}s elapsed")
    print(f"  Trades executed today: {len(executed)}")
    print(f"  Open positions: {len(monitor_result.get('still_open', []))}")
    print(f"  Closed today:   {len(monitor_result.get('closed', []))}")
    print(f"{'=' * 60}\n")
 
 
if __name__ == '__main__':
    run_all()
 
