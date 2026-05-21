"""
Prometheus Phase 2 — Script 4: Analysis Agent
Synthesises all research data and generates ITPM-style trade theses via Claude API
Output: data/trade_theses.json  +  data/trade_theses_YYYYMMDD_HHMM.json
"""
import anthropic
import json
import os
import re
from datetime import datetime
from dotenv import load_dotenv
 
load_dotenv()
 
client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
 
SYSTEM_PROMPT = """You are the Analysis Agent for Prometheus, an AI prop trading system built on ITPM methodology.

CRITICAL RULE — INSTRUMENT SELECTION:
- Sector ETFs (XLK, XLF, XLV, XLE, XLI, XLB, XLU, XLRE, XLY, XLP, XLC) are SCREENING TOOLS ONLY.
- NEVER recommend a trade on a sector ETF itself.
- NEVER recommend a trade on QQQ, SPY, IWM or any broad market ETF.
- All trade ideas must be on single-name US-listed stocks (e.g. NVDA, AAPL, XOM, JPM).

Core ITPM rules:
- Long the BEST individual stocks in the BEST sectors.
- Short the WORST individual stocks in the WORST sectors.
- Use options to maximise asymmetric risk/reward on high-conviction catalysts.
- EVERY trade needs: pre-committed thesis, specific catalyst, explicit invalidation conditions, hard time limit.
- Only generate ideas where AT LEAST 2 signals converge.

POSITION SIZING — ITPM METHOD (CRITICAL):
The Risk Manager uses RISK-BASED SIZING. Your job is to provide:
1. An estimated entry price (current approximate price of the stock)
2. A specific stop price in the invalidation conditions (e.g. "closes below $118")
The Risk Manager calculates: Max loss = 0.5% of portfolio / Risk per share = Entry - Stop
This determines the actual position size. Your position_size_pct is a SUGGESTION only.

INVALIDATION CONDITIONS — MUST BE SPECIFIC:
Always include at least one SPECIFIC PRICE LEVEL in invalidation conditions.
Good: "Stock closes below $118 (prior support), OR XLK drops below 50-day MA"
Bad: "If the thesis changes" or "if momentum weakens"
The price level is used as the automated stop. Without it, sizing falls back to conviction-based.

CATALYST EXIT:
Define exactly what a successful catalyst looks like and when.
The monitor will evaluate taking profit if the position is up >8% and catalyst appears to have fired.

Options strategy rules:
- IV above 70th percentile: vertical spread
- IV below 30th percentile: long call or put
- Earnings catalyst: compare ATM straddle vs historical move
- Entry: 45-60 DTE. Manage at 21 DTE.

Output fields per trade:
- ticker (individual stock only)
- direction (LONG or SHORT)
- conviction (HIGH / MEDIUM / LOW)
- sector (which sector ETF)
- entry_price (estimated current price — your best estimate)
- core_thesis
- catalyst (specific event + timing + what success looks like)
- options_structure
- invalidation_conditions (MUST include specific price level for stop)
- hard_time_limit
- position_size_pct (suggestion: HIGH=4%, MEDIUM=3%, LOW=2%)

Generate 2-3 ideas. Only where 2+ signals align.
Respond ONLY with valid JSON array. No markdown. No preamble.""" 
 
def load_data():
    data = {}
    for fname in ['sector_ranking.json', 'institutional_flow.json', 'unusual_whales_flow.json']:
        path = f'data/{fname}'
        if os.path.exists(path):
            with open(path) as f:
                data[fname.replace('.json', '')] = json.load(f)
            print(f"  Loaded {fname}")
        else:
            print(f"  WARNING: {fname} missing — run earlier scripts first")
    return data
 
 
def build_prompt(data):
    parts = []
 
    if 'sector_ranking' in data:
        sr = data['sector_ranking']
        top3    = sr.get('top_sectors', [])[:3]
        bottom3 = sr.get('bottom_sectors', [])
        parts.append("=== SECTOR RANKING (today) ===")
        parts.append("TOP SECTORS:")
        for s in top3:
            parts.append(f"  #{s['rank']} {s['ticker']} ({s['name']})  1w:{s['return_1w']:+.1f}%  1m:{s['return_1m']:+.1f}%  3m:{s['return_3m']:+.1f}%  score:{s['composite_score']:+.2f}%")
        parts.append("WEAK SECTORS:")
        for s in bottom3:
            parts.append(f"  #{s['rank']} {s['ticker']} ({s['name']})  score:{s['composite_score']:+.2f}%")
 
    if 'unusual_whales_flow' in data:
        uw  = data['unusual_whales_flow']
        summ = uw.get('summary', {})
        parts.append("\n=== UNUSUAL WHALES FLOW (today) ===")
        parts.append(f"Large dark pool prints (>$1M): {summ.get('large_darkpool_prints', 0)}")
        dp_tickers = summ.get('top_darkpool_tickers', [])
        if dp_tickers:
            parts.append(f"Dark pool tickers: {', '.join(dp_tickers)}")
        parts.append(f"Significant options flow (>$500k): {summ.get('significant_options_flow', 0)}")
        flow_tickers = summ.get('top_flow_tickers', [])
        if flow_tickers:
            parts.append(f"Options flow tickers: {', '.join(flow_tickers)}")
 
        top_flow = uw.get('options_flow', [])[:8]
        if top_flow:
            parts.append("Top options flow details:")
            for f in top_flow:
                parts.append(f"  {f['ticker']} {f['call_put']} strike:{f['strike']} exp:{f['expiry']} premium:${f['premium_usd']:,} sentiment:{f['sentiment']}")
 
        top_dp = uw.get('dark_pool_prints', [])[:8]
        if top_dp:
            parts.append("Top dark pool prints:")
            for d in top_dp:
                parts.append(f"  {d['ticker']} {d['size']} shares @ ${d['price']}  notional:${d['notional_usd']:,}")
 
    if 'institutional_flow' in data:
        inst = data['institutional_flow']
        summ = inst.get('summary', {})
        parts.append(f"\n=== INSTITUTIONAL FILINGS ===")
        parts.append(f"13F filings last 45 days: {summ.get('total_13f', 0)}")
        parts.append(f"Form 4 insider filings last 14 days: {summ.get('total_insider', 0)}")
        recent = [f['entity'] for f in inst.get('recent_13f_filings', [])[:8] if f.get('entity')]
        if recent:
            parts.append(f"Recent institutional filers: {', '.join(recent)}")
 
    return '\n'.join(parts)
 
 
def run():
    print("[Analysis Agent] Loading research data...")
    data = load_data()
 
    if not data:
        print("[Analysis Agent] ERROR: No data found. Run scripts 1–3 first.")
        return None
 
    prompt = build_prompt(data)
 
    print("[Analysis Agent] Calling Claude API (15–30 seconds)...")
    try:
        msg = client.messages.create(
            model='claude-opus-4-7',
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{
                'role': 'user',
                'content': (
                    f"Today's research data:\n\n{prompt}\n\n"
                    "Generate 2–3 high-conviction ITPM trade theses as a JSON array."
                )
            }]
        )
        raw = msg.content[0].text.strip()
 
        # Parse JSON — handle if model wraps in fences
        try:
            theses = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            theses = json.loads(match.group()) if match else [{'raw_output': raw}]
 
        ts = datetime.now().strftime('%Y%m%d_%H%M')
        output = {
            'generated_at': datetime.now().isoformat(),
            'model':        'claude-opus-4-7',
            'theses':       theses,
            'research_snapshot': {
                'top_sectors':      data.get('sector_ranking', {}).get('top_sectors', [])[:3],
                'darkpool_tickers': data.get('unusual_whales_flow', {}).get('summary', {}).get('top_darkpool_tickers', []),
                'flow_tickers':     data.get('unusual_whales_flow', {}).get('summary', {}).get('top_flow_tickers', []),
            }
        }
 
        os.makedirs('data', exist_ok=True)
        with open('data/trade_theses.json', 'w') as f:
            json.dump(output, f, indent=2)
        with open(f'data/trade_theses_{ts}.json', 'w') as f:
            json.dump(output, f, indent=2)
 
        print(f"\n[Analysis Agent] Complete — {len(theses)} trade ideas generated.")
        print("=" * 60)
        for i, t in enumerate(theses):
            if isinstance(t, dict) and 'ticker' in t:
                print(f"\nTHESIS {i+1}: {t.get('ticker')}  {t.get('direction')}  [{t.get('conviction')}]")
                print(f"  Thesis   : {str(t.get('core_thesis',''))[:120]}")
                print(f"  Catalyst : {str(t.get('catalyst',''))[:100]}")
                print(f"  Options  : {str(t.get('options_structure',''))[:100]}")
                print(f"  Exit if  : {str(t.get('invalidation_conditions',''))[:100]}")
                print(f"  Deadline : {t.get('hard_time_limit','')}")
                print(f"  Size     : {t.get('position_size_pct','')}%")
        print("=" * 60)
        print(f"  Saved → data/trade_theses.json")
        print(f"  Archive → data/trade_theses_{ts}.json")
        return output
 
    except Exception as e:
        print(f"[Analysis Agent] ERROR: {e}")
        return None
 
if __name__ == '__main__':
    run()
