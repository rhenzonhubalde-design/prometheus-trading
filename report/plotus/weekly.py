"""
Weekly Plotus brief — emits a Mon→Sun-SGT narrative + data drop for Hermes.

Usage:
    python3 -m report.plotus.weekly

Cron (production VPS):
    15 8 * * 6  cd ~/prometheus && /usr/bin/python3 -m report.plotus.weekly

Window: same as report.weekly — Mon 00:00 → Sun 23:59 SGT of the most
recently completed week (see report.stats.week_bounds_sgt).
"""
from __future__ import annotations

import sys, os, traceback
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from report import stats as _stats
from report import positions_loader, ibkr, db
from report.plotus import angles, data, generator, uploader


def main() -> int:
    print(f"[plotus.weekly] starting {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    conn = None
    try:
        conn = db.connect()
    except Exception as e:
        print(f"  [plotus.weekly] SQLite unavailable (history context skipped): {e}")

    success_any = False
    for data_dir, ib_port, label in positions_loader.ACCOUNTS:
        try:
            open_p, closed_p = positions_loader.load_account_positions(data_dir)
            acct_val, currency, prices = ibkr.fetch_account_value_and_prices(
                open_p, ib_port, label,
            )
            s = _stats.compute_weekly_stats(
                open_positions=open_p,
                closed_positions=closed_p,
                current_prices=prices,
                account_value=acct_val,
                account_label=label,
                currency=currency,
            )

            payload = data.build_weekly_payload(s, conn=conn)
            payload["angle"] = angles.pick_angle(payload)
            print(f"  [plotus.weekly] window {payload['week_start']} → {payload['week_end']}  "
                  f"angle={payload['angle']}  "
                  f"opened={payload['opened_count']} closed={payload['closed_count']} "
                  f"WR={payload.get('win_rate_pct')}")

            brief = generator.generate_brief(payload)
            uploader.publish(payload["date"], brief, payload)
            success_any = True

        except Exception as e:
            print(f"  [plotus.weekly] failed for {label}: {e}")
            traceback.print_exc()

    if conn is not None:
        conn.close()

    print("[plotus.weekly] done")
    return 0 if success_any else 1


if __name__ == '__main__':
    sys.exit(main())
