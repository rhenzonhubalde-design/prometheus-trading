"""
Prometheus reporting package — standalone daily and weekly Telegram reports.

This package is intentionally isolated from the trading strategy. It does not
import from phase1/2/3 or run_parallel.py, and the strategy does not import
from here. The only contract is the on-disk format of:
  - account_a/data/open_positions.json
  - account_a/data/closed_positions.json
  - account_b/data/open_positions.json
  - account_b/data/closed_positions.json

Entry points (run via cron):
  python3 -m reporting.daily   — daily per-account snapshot
  python3 -m reporting.weekly  — weekly per-account summary (fire Sat AM SGT)
"""
