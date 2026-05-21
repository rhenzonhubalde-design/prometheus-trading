import sys, os
sys.path.insert(0, os.path.expanduser('~/prometheus'))
sys.path.insert(0, os.path.expanduser('~/prometheus/phase3'))
import json
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.expanduser('~/prometheus/.env'))
import telegram_alerts as tg

def load_json(path, default):
    if os.path.exists(path): 
        with open(path) as f: return json.load(f)
    return default

def calc_stats(data_dir):
    closed = load_json(os.path.join(data_dir, 'closed_positions.json'), [])
    open_p = load_json(os.path.join(data_dir, 'open_positions.json'), [])
    if not closed:
        return {'total_trades': len(open_p), 'closed': 0, 'overall_win_rate': 0, 'overall_avg_pnl': 0}
    wins = [p for p in closed if float(p.get('pnl_pct', 0)) > 0]
    avg  = sum(float(p.get('pnl_pct', 0)) for p in closed) / len(closed)
    return {'total_trades': len(open_p)+len(closed), 'closed': len(closed),
            'overall_win_rate': round(len(wins)/len(closed)*100, 1), 'overall_avg_pnl': round(avg, 2)}

stats_a = calc_stats(os.path.expanduser('~/prometheus/account_a/data'))
stats_b = calc_stats(os.path.expanduser('~/prometheus/account_b/data'))
tg.send_ab_weekly_summary(stats_a, stats_b)
print("Weekly A/B report sent.")
