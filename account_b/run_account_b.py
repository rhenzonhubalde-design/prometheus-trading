"""
Prometheus — Account B Pipeline (Self-Improving / Learning)
Runs the full trading pipeline for the LEARNING paper account.
self_improving: true — historical journal insights injected into Analysis Agent.
Connects to IB Gateway on port 4003.
"""
import json
import os
import sys
from datetime import datetime, date

# ── Paths ──────────────────────────────────────────────────────────────────
ACCOUNT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR    = os.path.dirname(ACCOUNT_DIR)
PHASE2_DIR  = os.path.join(BASE_DIR, 'phase2')
PHASE3_DIR  = os.path.join(BASE_DIR, 'phase3')

sys.path.insert(0, ACCOUNT_DIR)
sys.path.insert(0, PHASE3_DIR)
sys.path.insert(0, PHASE2_DIR)

os.environ['PROMETHEUS_DATA_DIR'] = os.path.join(ACCOUNT_DIR, 'data')
os.environ['IB_PORT']             = '4003'
os.environ['IB_CLIENT_EXEC']      = '3'
os.environ['IB_CLIENT_MONITOR']   = '4'
os.environ['ACCOUNT_LABEL']       = 'LEARNING'
os.environ['LEARNING_MODE']       = 'with_learning'

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.expanduser('~/prometheus/.env'))

# Import Account A's shared helpers
sys.path.insert(0, os.path.join(BASE_DIR, 'account_a'))
from run_account_a import _run_monitor, _run_journal, should_run_journal, load_json


def generate_learning_theses():
    """
    Run the Analysis Agent with learning insights injected.
    Reads from the same research data as Account A but enhances with journal.
    Saves to phase2/data/trade_theses_b.json (separate from Account A's theses).
    """
    import re, anthropic

    client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    data_dir    = os.environ['PROMETHEUS_DATA_DIR']
    config_path = os.path.join(ACCOUNT_DIR, 'prometheus_config.json')

    SYSTEM_PROMPT = """You are the Analysis Agent for Prometheus Account B (LEARNING mode).

CRITICAL RULE: Only recommend trades on individual US-listed stocks.
NEVER trade sector ETFs (XLK, XLF, XLV etc.) or broad market ETFs (QQQ, SPY).

ITPM rules:
- Long the BEST stocks in the BEST sectors. Short WORST in WORST sectors.
- Only generate ideas where AT LEAST 2 signals converge.
- Every trade needs: thesis, catalyst, invalidation conditions, hard time limit.
- IV below 30th percentile: buy calls/puts. IV above 70th: vertical spreads.
- Entry: 45-60 DTE. Manage at 21 DTE.

Output fields per trade: ticker, direction (LONG/SHORT), conviction (HIGH/MEDIUM/LOW),
sector, core_thesis, catalyst, options_structure, invalidation_conditions,
hard_time_limit, position_size_pct (max 5%).

Generate 2-3 ideas. Respond ONLY with a valid JSON array. No markdown."""

    # Build research prompt (same as Account A)
    parts = []
    for fname in ['sector_ranking.json', 'institutional_flow.json', 'unusual_whales_flow.json']:
        path = os.path.join(PHASE2_DIR, 'data', fname)
        if os.path.exists(path):
            with open(path) as f:
                d = json.load(f)
            if 'sector_ranking' in fname:
                top3 = d.get('top_sectors', [])[:3]
                bot3 = d.get('bottom_sectors', [])
                parts.append("=== SECTOR RANKING ===")
                for s in top3:
                    parts.append(f"  #{s['rank']} {s['ticker']} ({s['name']}) score:{s['composite_score']:+.2f}%")
                parts.append("WORST:")
                for s in bot3:
                    parts.append(f"  #{s['rank']} {s['ticker']} score:{s['composite_score']:+.2f}%")
            elif 'unusual_whales' in fname:
                summ = d.get('summary', {})
                parts.append("\n=== UNUSUAL WHALES FLOW ===")
                dp = summ.get('top_darkpool_tickers', [])
                fl = summ.get('top_flow_tickers', [])
                if dp: parts.append(f"Dark pool: {', '.join(dp)}")
                if fl: parts.append(f"Options flow: {', '.join(fl)}")
            elif 'institutional' in fname:
                summ = d.get('summary', {})
                parts.append(f"\n=== INSTITUTIONAL ===")
                parts.append(f"13F filings: {summ.get('total_13f',0)} | Insider: {summ.get('total_insider',0)}")

    research_prompt = '\n'.join(parts)

    # ── Inject learning insights ───────────────────────────────
    learning_block = ''
    journal  = load_json(os.path.join(data_dir, 'trade_journal.json'), [])
    stats    = load_json(os.path.join(data_dir, 'performance_stats.json'), {})

    if len(journal) >= 1:
        lines = ["\n=== HISTORICAL LEARNING INSIGHTS (Account B — self-improving) ==="]
        lines.append(f"Based on {len(journal)} reviewed trade(s):\n")

        by_conv = stats.get('by_conviction', {})
        if by_conv:
            lines.append("CONVICTION PERFORMANCE:")
            for conv, data in sorted(by_conv.items(), key=lambda x: x[1].get('avg_pnl',0), reverse=True):
                if data.get('trades', 0) >= 1:
                    lines.append(f"  {conv}: {data['trades']} trades | {data.get('win_rate',0)}% wins | avg {data.get('avg_pnl',0):+.1f}%")

        winning = stats.get('winning_patterns', {})
        if winning:
            top = sorted(winning.items(), key=lambda x: x[1], reverse=True)[:5]
            lines.append("\nPATTERNS THAT WORKED:")
            for tag, cnt in top:
                lines.append(f"  {tag}: {cnt} winning trade(s)")

        losing = stats.get('losing_patterns', {})
        if losing:
            top = sorted(losing.items(), key=lambda x: x[1], reverse=True)[:3]
            lines.append("\nPATTERNS TO AVOID:")
            for tag, cnt in top:
                lines.append(f"  {tag}: {cnt} losing trade(s)")

        lessons = stats.get('top_lessons', [])[:3]
        if lessons:
            lines.append("\nKEY LESSONS:")
            for l in lessons:
                if l: lines.append(f"  - {l}")

        lines.append("\nINSTRUCTION: Use these insights to refine thesis quality.")
        lines.append("Weight setups matching winning patterns. Avoid losing patterns.")
        lines.append("=== END INSIGHTS ===\n")
        learning_block = '\n'.join(lines)
        print(f"  Learning insights injected ({len(journal)} reviewed trades)")
    else:
        print("  No journal data yet — running as standard (first trade cycle)")

    full_prompt = f"Today's research:\n\n{research_prompt}{learning_block}\n\nGenerate 2-3 ITPM trade theses as JSON array."

    try:
        msg = client.messages.create(
            model='claude-sonnet-4-20250514', max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': full_prompt}]
        )
        raw = msg.content[0].text.strip()
        try:
            theses = json.loads(raw)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            theses = json.loads(match.group()) if match else []

        for thesis in theses:
            thesis['learning_mode'] = 'with_learning'

        output = {
            'generated_at':  datetime.now().isoformat(),
            'account':       'B',
            'learning_mode': 'with_learning',
            'theses':        theses,
        }
        save_path = os.path.join(PHASE2_DIR, 'data', 'trade_theses_b.json')
        with open(save_path, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"  {len(theses)} learning-enhanced theses generated")
        return output
    except Exception as e:
        print(f"  Analysis Agent failed: {e}")
        return {}


def run():
    import telegram_alerts as tg

    data_dir    = os.environ['PROMETHEUS_DATA_DIR']
    config_path = os.path.join(ACCOUNT_DIR, 'prometheus_config.json')
    os.makedirs(data_dir, exist_ok=True)

    start = datetime.now()
    print("\n" + "─" * 50)
    print(f"  ACCOUNT B — LEARNING — {start.strftime('%H:%M')}")
    print("─" * 50)

    # ── Generate learning-enhanced theses ─────────────────────
    print("[B-1/4] Analysis Agent (learning mode)...")
    theses_output = generate_learning_theses()
    theses = theses_output.get('theses', [])

    # ── Risk Manager ──────────────────────────────────────────
    print("[B-2/4] Risk Manager...")
    risk_result = None
    try:
        from risk_manager import validate_thesis
        import json as _j

        open_positions = load_json(os.path.join(data_dir, 'open_positions.json'), [])
        approved, rejected = [], []
        for thesis in theses:
            passed, messages = validate_thesis(thesis, open_positions)
            result = {**thesis, 'risk_check_time': datetime.now().isoformat(),
                      'risk_checks': messages, 'approved': passed}
            (approved if passed else rejected).append(result)
            print(f"  {'✓' if passed else '✗'} {thesis.get('ticker')} {thesis.get('direction')}")

        with open(os.path.join(data_dir, 'approved_trades.json'), 'w') as f:
            _j.dump({'generated_at': datetime.now().isoformat(), 'trades': approved}, f, indent=2)
        with open(os.path.join(data_dir, 'rejected_trades.json'), 'w') as f:
            _j.dump({'generated_at': datetime.now().isoformat(), 'trades': rejected}, f, indent=2)

        risk_result = {'approved': approved, 'rejected': rejected}
        print(f"  Approved: {len(approved)} | Rejected: {len(rejected)}")
    except Exception as e:
        print(f"  Risk Manager failed: {e}")

    # ── Execution ─────────────────────────────────────────────
    executed = []
    approved_count = len((risk_result or {}).get('approved', []))
    if approved_count > 0:
        print(f"[B-3/4] Executing {approved_count} trade(s) on Account B...")
        try:
            from ib_insync import IB, Stock, LimitOrder
            import math

            ib = IB()
            ib.connect('127.0.0.1', int(os.environ['IB_PORT']),
                       clientId=int(os.environ['IB_CLIENT_EXEC']))

            account_vals  = ib.accountValues()
            account_value = 100_000
            for av in account_vals:
                if av.tag == 'NetLiquidation' and av.currency == 'USD':
                    account_value = float(av.value)

            open_positions = load_json(os.path.join(data_dir, 'open_positions.json'), [])

            for thesis in risk_result['approved']:
                ticker    = thesis.get('ticker', '')
                direction = thesis.get('direction', 'LONG')
                size_pct  = float(thesis.get('position_size_pct', 3.0))
                size_usd  = account_value * (size_pct / 100)
                try:
                    contract = Stock(ticker, 'SMART', 'USD')
                    ib.qualifyContracts(contract)
                    td = ib.reqMktData(contract, '', False, False)
                    ib.sleep(3)
                    bid = td.bid or 0
                    ask = td.ask or 0
                    price = round((bid+ask)/2, 2) if (bid>0 and ask>0 and not math.isnan(bid)) else 0
                    if not price:
                        for attr in ['last','close']:
                            v = getattr(td, attr, None)
                            if v and not math.isnan(v) and v > 0:
                                price = round(v, 2); break
                    if not price:
                        print(f"  No price for {ticker}"); continue

                    qty    = max(1, int(size_usd / price))
                    action = 'BUY' if direction == 'LONG' else 'SELL'
                    order  = LimitOrder(action, qty, price)
                    order.tif = 'DAY'
                    trade  = ib.placeOrder(contract, order)
                    ib.sleep(2)

                    from datetime import timedelta
                    position = {**thesis, 'entry_date': datetime.now().strftime('%Y-%m-%d'),
                                'entry_time': datetime.now().isoformat(), 'entry_price': price,
                                'entry_qty': qty, 'entry_size_usd': round(size_usd,2),
                                'order_id': trade.order.orderId, 'status': 'open',
                                'paper_trade': True, 'account': 'B_LEARNING',
                                'learning_mode': 'with_learning',
                                'deadline_date': (datetime.now()+timedelta(days=45)).strftime('%Y-%m-%d')}
                    open_positions.append(position)
                    executed.append(position)
                    tg.send_trade_opened_labeled(thesis, {'qty':qty,'limit_price':price,
                                                  'status':trade.orderStatus.status}, account_value, 'B — LEARNING')
                    print(f"  ✓ {action} {qty} {ticker} @ ${price}")
                except Exception as ex:
                    print(f"  Trade failed {ticker}: {ex}")

            ib.disconnect()
            import json as _j
            with open(os.path.join(data_dir, 'open_positions.json'), 'w') as f:
                _j.dump(open_positions, f, indent=2)
        except Exception as e:
            print(f"  Execution failed: {e}")
    else:
        print("[B-3/4] No approved trades.")

    # ── Monitor ───────────────────────────────────────────────
    print("[B-4/4] Monitor Agent...")
    monitor_result = {'still_open': [], 'closed': []}
    try:
        monitor_result = _run_monitor(data_dir) or monitor_result
    except Exception as e:
        print(f"  Monitor failed: {e}")

    # ── Journal (weekly) ──────────────────────────────────────
    if should_run_journal(config_path):
        print("[B-5/4] Journal Agent (weekly)...")
        try:
            _run_journal(data_dir, config_path, 'with_learning')
        except Exception as e:
            print(f"  Journal failed: {e}")

    elapsed = (datetime.now() - start).seconds
    print(f"  Account B complete — {elapsed}s | "
          f"{len(executed)} executed | "
          f"{len(monitor_result.get('still_open',[]))} open")

    return {
        'executed':     executed,
        'monitor':      monitor_result,
        'approved':     approved_count,
        'theses_count': len(theses),
    }


if __name__ == '__main__':
    run()
