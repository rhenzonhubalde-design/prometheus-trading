"""
Prometheus Phase 3 — Script 1: Risk Manager Agent
Validates every trade thesis against hard risk rules before allowing execution.
Output: data/approved_trades.json  +  data/rejected_trades.json
"""
import json
import os
from datetime import datetime
 
# ── Hard risk rules ────────────────────────────────────────────────────────
MAX_POSITION_PCT       = 5.0   # max % of portfolio in any single name
MAX_SECTOR_PCT         = 20.0  # max % of portfolio in any single sector
MAX_CORRELATED_NAMES   = 5     # max number of open positions at once
MAX_TOTAL_DELTA_PCT    = 30.0  # max net directional exposure (long - short) as % of portfolio
 
SECTOR_MAP = {
    'XLK': 'Technology',    'XLF': 'Financials',     'XLV': 'Healthcare',
    'XLE': 'Energy',        'XLI': 'Industrials',    'XLB': 'Materials',
    'XLU': 'Utilities',     'XLRE': 'Real Estate',   'XLY': 'Consumer Discretionary',
    'XLP': 'Consumer Staples', 'XLC': 'Communication Services',
}
 
 
def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default
 
 
def get_sector_from_thesis(thesis):
    """Extract sector ETF ticker from thesis sector field e.g. 'XLK (Technology)' -> 'XLK'"""
    sector_field = thesis.get('sector', '')
    for etf in SECTOR_MAP:
        if etf in sector_field:
            return etf
    return 'UNKNOWN'
 
 
def check_position_size(thesis):
    size = float(thesis.get('position_size_pct', 0))
    if size > MAX_POSITION_PCT:
        return False, f"Position size {size}% exceeds max {MAX_POSITION_PCT}%"
    if size <= 0:
        return False, "Position size is 0 or missing"
    return True, f"Position size {size}% OK"
 
 
def check_sector_concentration(thesis, open_positions):
    sector = get_sector_from_thesis(thesis)
    new_size = float(thesis.get('position_size_pct', 0))
 
    existing_sector_pct = sum(
        float(p.get('position_size_pct', 0))
        for p in open_positions
        if get_sector_from_thesis(p) == sector
    )
    total = existing_sector_pct + new_size
    if total > MAX_SECTOR_PCT:
        return False, f"Sector {sector} would be {total:.1f}% — exceeds max {MAX_SECTOR_PCT}%"
    return True, f"Sector {sector} concentration {total:.1f}% OK"
 
 
def check_correlated_names(open_positions):
    if len(open_positions) >= MAX_CORRELATED_NAMES:
        return False, f"Already have {len(open_positions)} open positions — max is {MAX_CORRELATED_NAMES}"
    return True, f"Open positions {len(open_positions)}/{MAX_CORRELATED_NAMES} OK"
 
 
def check_duplicate(thesis, open_positions):
    ticker = thesis.get('ticker', '').upper()
    for p in open_positions:
        if p.get('ticker', '').upper() == ticker:
            return False, f"{ticker} already has an open position"
    return True, f"No duplicate for {ticker}"
 
 
def check_delta_exposure(thesis, open_positions):
    """Simple delta check — longs add positive delta, shorts add negative"""
    current_delta = sum(
        float(p.get('position_size_pct', 0)) * (1 if p.get('direction') == 'LONG' else -1)
        for p in open_positions
    )
    new_delta = float(thesis.get('position_size_pct', 0)) * (1 if thesis.get('direction') == 'LONG' else -1)
    total_delta = abs(current_delta + new_delta)
    if total_delta > MAX_TOTAL_DELTA_PCT:
        return False, f"Net delta {total_delta:.1f}% would exceed max {MAX_TOTAL_DELTA_PCT}%"
    return True, f"Net delta {total_delta:.1f}% OK"
 
 
def validate_thesis(thesis, open_positions):
    checks = [
        check_duplicate(thesis, open_positions),
        check_position_size(thesis),
        check_sector_concentration(thesis, open_positions),
        check_correlated_names(open_positions),
        check_delta_exposure(thesis, open_positions),
    ]
    passed = all(ok for ok, _ in checks)
    messages = [msg for _, msg in checks]
    return passed, messages
 
 
def run():
    print("[Risk Manager] Loading trade theses and open positions...")
 
    theses_data = load_json('../phase2/data/trade_theses.json', {})
    theses = theses_data.get('theses', [])
    if not theses:
        print("[Risk Manager] No theses found. Run Phase 2 pipeline first.")
        return
 
    open_positions = load_json('data/open_positions.json', [])
    print(f"  {len(theses)} theses to evaluate | {len(open_positions)} positions currently open")
 
    approved, rejected = [], []
 
    for thesis in theses:
        ticker = thesis.get('ticker', 'UNKNOWN')
        passed, messages = validate_thesis(thesis, open_positions)
 
        result = {
            **thesis,
            'risk_check_time': datetime.now().isoformat(),
            'risk_checks':     messages,
            'approved':        passed,
        }
 
        if passed:
            approved.append(result)
            print(f"  ✓ APPROVED  {ticker} {thesis.get('direction')} [{thesis.get('conviction')}]")
            for m in messages:
                print(f"      {m}")
        else:
            rejected.append(result)
            print(f"  ✗ REJECTED  {ticker} {thesis.get('direction')}")
            for m in messages:
                print(f"      {m}")
 
    os.makedirs('data', exist_ok=True)
    with open('data/approved_trades.json', 'w') as f:
        json.dump({'generated_at': datetime.now().isoformat(), 'trades': approved}, f, indent=2)
    with open('data/rejected_trades.json', 'w') as f:
        json.dump({'generated_at': datetime.now().isoformat(), 'trades': rejected}, f, indent=2)
 
    print(f"\n[Risk Manager] Complete — {len(approved)} approved, {len(rejected)} rejected")
    print(f"  Approved → data/approved_trades.json")
    return {'approved': approved, 'rejected': rejected}
 
 
if __name__ == '__main__':
    run()
