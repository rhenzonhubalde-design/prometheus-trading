"""
Daily Plotus brief — emits a narrative + data drop to Google Drive for Hermes.

Usage:
    python3 -m report.plotus.daily

Cron (production VPS — runs every day, including weekends/holidays):
    15 5 * * *  cd ~/prometheus && /usr/bin/python3 -m report.plotus.daily

What it does:
    1. Read open + closed positions and today's risk-gate decisions (Account A).
    2. Fetch live prices + NetLiq via report.ibkr.
    3. Compute daily stats via report.stats.compute_daily_stats.
    4. Project into the publication-safe percentages-only payload.
    5. Pick the editorial angle from what actually happened.
    6. Generate the narrative brief.md via Claude (or template fallback).
    7. Write the drop locally + push to gdrive:AI Trading/Plotus/Briefs/{date}/.
"""
from __future__ import annotations

import sys, os, traceback
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Match the trading agents' pattern: load ANTHROPIC_API_KEY from ~/prometheus/.env
# so Claude narrative writing works under cron (which doesn't inherit a shell env).
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.expanduser('~/prometheus/.env'))
except ImportError:
    pass

from report import stats as _stats
from report import positions_loader, ibkr, db
from report.plotus import angles, data, generator, uploader


def main() -> int:
    print(f"[plotus.daily] starting {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    conn = None
    try:
        conn = db.connect()
    except Exception as e:
        print(f"  [plotus.daily] SQLite unavailable (history context skipped): {e}")

    # Single account in v2 — but loop the list so a future second account works.
    success_any = False
    for data_dir, ib_port, label in positions_loader.ACCOUNTS:
        try:
            open_p, closed_p   = positions_loader.load_account_positions(data_dir)
            approved, rejected = positions_loader.load_approved_rejected(data_dir)

            today_iso = _stats.today_sgt().isoformat()
            opened_today = [p for p in open_p   if (p.get('entry_date') or '')[:10] == today_iso]
            closed_today = [p for p in closed_p if (p.get('exit_date')  or '')[:10] == today_iso]

            acct_val, currency, prices = ibkr.fetch_account_value_and_prices(
                open_p, ib_port, label,
            )

            s = _stats.compute_daily_stats(
                open_positions=open_p,
                current_prices=prices,
                account_value=acct_val,
                account_label=label,
                currency=currency,
            )

            payload = data.build_daily_payload(
                s,
                opened_today=opened_today,
                closed_today=closed_today,
                approved_today=approved,
                rejected_today=rejected,
                conn=conn,
                data_dir=data_dir,
            )
            payload["angle"] = angles.pick_angle(payload)
            print(f"  [plotus.daily] angle={payload['angle']}  "
                  f"open={payload['open_count']}  "
                  f"opened={payload['trades_opened_today']}  "
                  f"closed={payload['trades_closed_today']}")

            brief = generator.generate_brief(payload)
            uploader.publish(payload["date"], brief, payload)
            success_any = True

        except Exception as e:
            print(f"  [plotus.daily] failed for {label}: {e}")
            traceback.print_exc()

    if conn is not None:
        conn.close()

    print("[plotus.daily] done")
    return 0 if success_any else 1


if __name__ == '__main__':
    sys.exit(main())
