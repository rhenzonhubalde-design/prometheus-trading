"""
Prometheus Phase 3 — Monitor Agent (Autonomous)
Runs daily. Checks every open position against its pre-committed thesis.
Exits automatically if invalidation triggers or deadline passes.
Sends Telegram notification explaining every exit decision.
"""
import json
import os
import sys
from datetime import datetime
import anthropic
from dotenv import load_dotenv
 
load_dotenv(dotenv_path=os.path.expanduser('~/prometheus/.env'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
 
import telegram_alerts as tg
from ib_insync import IB, Stock, LimitOrder
 
IB_HOST      = os.getenv('IB_HOST', '127.0.0.1')
IB_PORT      = int(os.getenv('IB_PORT', 4002))
IB_CLIENT_ID = 4
 
claude = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
 
 
def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default
 
 
def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
 
 
def get_current_price(ib, ticker):
    try:
        contract = Stock(ticker, 'SMART', 'USD')
        ib.qualifyContracts(contract)
        tdata = ib.reqMktData(contract, '', False, False)
        ib.sleep(2)
        for attr in ['last', 'close', 'bid']:
            val = getattr(tdata, attr, None)
            if val and val > 0:
                return float(val)
    except Exception as e:
        print(f"    Price error for {ticker}: {e}")
    return None
 
 
def check_deadline(position):
    deadline_str = position.get('deadline_date', '')
    if not deadline_str:
        return False
    try:
        deadline = datetime.strptime(deadline_str[:10], '%Y-%m-%d')
        return datetime.now() > deadline
    except Exception:
        return False
 
 
def check_21dte(position):
    entry_date_str = position.get('entry_date', '')
    if not entry_date_str:
        return False
    try:
        entry_date = datetime.strptime(entry_date_str, '%Y-%m-%d')
        days_held  = (datetime.now() - entry_date).days
        return days_held >= 24 and position.get('instrument') == 'options'
    except Exception:
        return False
 
 
def check_invalidation_with_claude(position, current_price):
    ticker      = position.get('ticker', '')
    direction   = position.get('direction', '')
    entry_price = float(position.get('entry_price', 0))
    conditions  = position.get('invalidation_conditions', '')
    thesis      = position.get('core_thesis', '')
    entry_date  = position.get('entry_date', '2026-01-01')
 
    pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price else 0
    if direction == 'SHORT':
        pnl_pct = -pnl_pct
 
    try:
        days_held = (datetime.now() - datetime.strptime(entry_date, '%Y-%m-%d')).days
    except Exception:
        days_held = 0
 
    prompt = f"""You are the Monitor Agent for Prometheus, an AI prop trading system.
 
OPEN POSITION:
Ticker:        {ticker}
Direction:     {direction}
Entry price:   ${entry_price}
Current price: ${current_price:.2f}
P&L:           {pnl_pct:+.1f}%
Days held:     {days_held}
 
ORIGINAL THESIS:
{thesis}
 
INVALIDATION CONDITIONS (exit immediately if any triggered):
{conditions}
 
TASK:
Has any invalidation condition been triggered based on the current price and days held?
Be strict - if a price level is clearly breached, mark it as triggered.
 
Respond ONLY with valid JSON, no markdown:
{{
  "invalidation_triggered": true or false,
  "condition_triggered": "which specific condition fired, or null if none",
  "reasoning": "1-2 sentence explanation",
  "recommended_action": "HOLD" or "EXIT"
}}"""
 
    try:
        msg = claude.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=300,
            messages=[{'role': 'user', 'content': prompt}]
        )
        raw = msg.content[0].text.strip()
        return json.loads(raw)
    except Exception as e:
        print(f"    Claude check error: {e}")
        return {
            'invalidation_triggered': False,
            'recommended_action': 'HOLD',
            'reasoning': f'Check failed: {e}',
            'condition_triggered': None
        }
 
 
def close_position(ib, position, exit_price):
    ticker    = position.get('ticker', '')
    direction = position.get('direction', '')
    qty       = position.get('entry_qty', 1)
 
    try:
        contract = Stock(ticker, 'SMART', 'USD')
        ib.qualifyContracts(contract)
 
        close_action = 'SELL' if direction == 'LONG' else 'BUY'
        limit_price  = round(exit_price * (0.998 if close_action == 'SELL' else 1.002), 2)
 
        order = LimitOrder(close_action, qty, limit_price)
        order.tif = 'DAY'
        ib.placeOrder(contract, order)
        ib.sleep(2)
        print(f"    Closing order placed: {close_action} {qty} {ticker} @ ${limit_price}")
        return limit_price
    except Exception as e:
        print(f"    Close order error: {e}")
        return exit_price
 
 
def run():
    print("[Monitor Agent] Checking open positions...")
 
    open_positions   = load_json('data/open_positions.json', [])
    closed_positions = load_json('data/closed_positions.json', [])
 
    if not open_positions:
        print("[Monitor Agent] No open positions to monitor.")
        return {'still_open': [], 'closed': []}
 
    print(f"  {len(open_positions)} open position(s) to check")
 
    print("[Monitor Agent] Connecting to IBKR...")
    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID)
        print(f"  Connected. Account: {ib.managedAccounts()}")
    except Exception as e:
        print(f"  IBKR connection failed: {e}")
        tg.send(f"MONITOR ERROR - Could not connect to IBKR.\n{e}")
        return {'still_open': open_positions, 'closed': []}
 
    still_open   = []
    newly_closed = []
 
    for position in open_positions:
        ticker      = position.get('ticker', '')
        direction   = position.get('direction', '')
        entry_price = float(position.get('entry_price', 0))
        entry_date  = position.get('entry_date', '')
 
        print(f"\n  Checking {ticker} {direction} (entered {entry_date})...")
 
        current_price = get_current_price(ib, ticker)
        if not current_price:
            print(f"    Could not get price - holding")
            still_open.append(position)
            continue
 
        pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price else 0
        if direction == 'SHORT':
            pnl_pct = -pnl_pct
        print(f"    Price: ${current_price:.2f} | Entry: ${entry_price} | P&L: {pnl_pct:+.1f}%")
 
        exit_reason = None
 
        # 1. Hard deadline
        if check_deadline(position):
            exit_reason = f"Hard time limit reached ({position.get('deadline_date','')}). Exiting regardless of P&L as per pre-committed thesis rules."
 
        # 2. 21 DTE options management
        elif check_21dte(position):
            exit_reason = "21 DTE reached - exiting to avoid accelerating theta decay."
 
        # 3. Claude invalidation check
        else:
            result = check_invalidation_with_claude(position, current_price)
            print(f"    Monitor verdict: {result.get('recommended_action')} - {result.get('reasoning','')[:100]}")
 
            if result.get('invalidation_triggered') and result.get('recommended_action') == 'EXIT':
                exit_reason = result.get('condition_triggered', 'Invalidation condition triggered')
                tg.send_invalidation(position, exit_reason)
 
        if exit_reason:
            print(f"    EXITING: {exit_reason}")
            actual_exit_price = close_position(ib, position, current_price)
 
            closed = {
                **position,
                'exit_date':   datetime.now().strftime('%Y-%m-%d'),
                'exit_time':   datetime.now().isoformat(),
                'exit_price':  actual_exit_price,
                'exit_reason': exit_reason,
                'pnl_pct':     round(pnl_pct, 2),
                'status':      'closed',
            }
            closed_positions.append(closed)
            newly_closed.append(closed)
            tg.send_trade_closed(position, exit_reason, pnl_pct)
        else:
            print(f"    HOLDING - thesis intact")
            still_open.append(position)
 
    ib.disconnect()
 
    save_json('data/open_positions.json', still_open)
    save_json('data/closed_positions.json', closed_positions)
 
    print(f"\n[Monitor Agent] Complete")
    print(f"  Still open:   {len(still_open)}")
    print(f"  Closed today: {len(newly_closed)}")
 
    return {'still_open': still_open, 'closed': newly_closed}
 
 
if __name__ == '__main__':
    run()
 
