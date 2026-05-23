"""
Read-only helpers for loading position JSON files written by the trading
strategy. The reporting package never writes to these paths.
"""
import json
import os
from typing import Tuple


BASE_DIR = os.path.expanduser('~/prometheus')

ACCOUNTS = [
    # (data_dir, ib_port, account_label)
    (os.path.join(BASE_DIR, 'account_a', 'data'), 4002, 'A — BASELINE'),
    (os.path.join(BASE_DIR, 'account_b', 'data'), 4003, 'B — LEARNING'),
]


def load_json(path: str, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def load_account_positions(data_dir: str) -> Tuple[list, list]:
    """Returns (open_positions, closed_positions) for one account."""
    open_p   = load_json(os.path.join(data_dir, 'open_positions.json'),   [])
    closed_p = load_json(os.path.join(data_dir, 'closed_positions.json'), [])
    return open_p, closed_p
