"""
Daily per-account Telegram report.

Usage:
  python3 -m reporting.daily

Cron (suggested — fire ~30min after run_parallel.py completes):
  30 21 * * 1-5  cd ~/prometheus && /usr/bin/python3 -m reporting.daily

Reads:  account_a/data/open_positions.json
        account_b/data/open_positions.json
        IBKR live prices + NetLiquidation
Writes: nothing on disk; sends 2 Telegram messages (one per account).
"""
import sys, os, traceback

# Allow `python3 -m reporting.daily` from the repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reporting import stats, messages, telegram, data, ibkr


def run_for_account(data_dir: str, ib_port: int, label: str) -> None:
    open_p, _   = data.load_account_positions(data_dir)
    acct_val, currency, prices = ibkr.fetch_account_value_and_prices(
        open_p, ib_port, label
    )
    s = stats.compute_daily_stats(
        open_positions=open_p,
        current_prices=prices,
        account_value=acct_val,
        account_label=label,
        currency=currency,
    )
    print(f"  [{label}] open={s['open_trades']}  "
          f"unreal={currency} {s['total_unrealized_usd']:+.2f}  "
          f"risk_live={currency} {s['live_risk_usd']:,.2f}")
    telegram.send(messages.build_daily_message(s))


def main() -> None:
    for data_dir, ib_port, label in data.ACCOUNTS:
        try:
            run_for_account(data_dir, ib_port, label)
        except Exception as e:
            print(f"[{label}] Daily report failed: {e}")
            traceback.print_exc()
    print("Daily per-account reports sent.")


if __name__ == '__main__':
    main()
