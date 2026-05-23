"""
Privacy sanitizer for Plotus public output.

Rule: nothing dollar-denominated ever leaves this module into a public brief.
The Instagram audience sees percentages (of account, of position) only.
NetLiq, position sizes, realized P&L in USD, and entry/exit prices are
account-revealing and must be stripped or converted to %.

`sanitize_payload`  — convert the dict returned by `build_payload` into a
                     publication-safe dict (removes $ keys, asserts no leaks).
`assert_no_dollar_leaks` — last-mile guardrail before brief.md ships:
                     scans free text for $-style figures or known leak tokens.

Tested in report/tests/test_plotus_sanitizer.py.
"""
from __future__ import annotations

import re
from typing import Any


# Keys allowed in publication output. Anything else is stripped — even when
# adding a new field upstream, the sanitizer will quietly drop it until it's
# listed here. That's by design: public output is opt-in.
PUBLIC_KEYS = frozenset({
    "date", "type", "angle",
    "open_count", "trades_opened_today", "trades_closed_today",
    "closed_today",                # list of {ticker, direction, pnl_pct, exit_reason}
    "opened_today",                # list of {ticker, direction, conviction}
    "approved_today", "rejected_today",
    "unrealized_pct_of_account", "unrealized_pct_avg_position",
    "budgeted_risk_pct_of_account", "live_risk_pct_of_account",
    "positions_missing_stop",
    "open_positions",              # list of {ticker, direction, unrealized_pct, days_held}
    # weekly-only
    "week_start", "week_end",
    "opened_count", "closed_count", "win_count", "loss_count", "win_rate_pct",
    "realized_pct_of_account",
    "best_trade", "worst_trade",   # {ticker, direction, pnl_pct, exit_reason}
    "open_count_eow",
    # context (optional, may be absent if research data missing)
    "top_sectors",                 # [{ticker, name}]  no scores
    # historical context
    "recent_win_rate_pct", "streak",
})

# Position-level keys allowed inside `open_positions`, `closed_today` etc.
POSITION_PUBLIC_KEYS = frozenset({
    "ticker", "direction", "conviction", "instrument",
    "pnl_pct", "unrealized_pct", "exit_reason", "days_held",
})

# Dollar-or-account-leak patterns: stripped/blocked at every layer.
_LEAK_KEY_PATTERNS = re.compile(
    r"(_usd$|_dollar|account_value|netliq|entry_price|exit_price|"
    r"entry_size|entry_qty|current_price|risk_per_share|calculated_stop|pnl_usd)",
    re.IGNORECASE,
)

# Free-text leak patterns for brief.md content.
#   $123, $1,234.56, USD 100, 1,000 USD, NetLiq 102k, account_value: 100000
_DOLLAR_RE      = re.compile(r"\$\s?-?\d[\d,]*(\.\d+)?")
_USD_NUMBER_RE  = re.compile(r"(?<![A-Za-z_])(USD|usd)\s+-?\d[\d,]*(\.\d+)?")
_NUMBER_USD_RE  = re.compile(r"-?\d[\d,]*(\.\d+)?\s+(USD|usd)(?![A-Za-z_])")
_LEAK_TOKENS    = re.compile(
    r"\b(NetLiq|NetLiquidation|account_value|account[\s_-]value|"
    r"entry_size|entry_price|pnl_usd)\b",
    re.IGNORECASE,
)


class LeakDetected(ValueError):
    """Raised when sanitization spots a $-figure or NetLiq token in public output."""


def _is_leak_key(key: str) -> bool:
    return bool(_LEAK_KEY_PATTERNS.search(key))


def sanitize_position(p: dict) -> dict:
    """Keep only POSITION_PUBLIC_KEYS, drop everything else."""
    return {k: v for k, v in p.items() if k in POSITION_PUBLIC_KEYS}


def sanitize_payload(payload: dict) -> dict:
    """
    Return a copy of `payload` with only PUBLIC_KEYS, with position-level
    lists stripped to POSITION_PUBLIC_KEYS. Raises LeakDetected if any
    leak-shaped key slips into the public output.
    """
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if k not in PUBLIC_KEYS:
            if _is_leak_key(k):
                # Caller passed a $ key under a name we'd allow if it weren't
                # leaky — refuse loudly rather than silently dropping.
                raise LeakDetected(f"refusing to publish leak-shaped key: {k!r}")
            continue
        if isinstance(v, list) and v and isinstance(v[0], dict):
            out[k] = [sanitize_position(p) for p in v]
        elif isinstance(v, dict):
            out[k] = sanitize_position(v) if k in {"best_trade", "worst_trade"} else v
        else:
            out[k] = v
    return out


def assert_no_dollar_leaks(text: str) -> None:
    """
    Final guardrail for free-form brief.md content.

    Catches: $123 / $1.2k / USD 100 / 1,000 USD / "NetLiq" / "account_value".
    Does NOT catch: percentages ("+12%"), bare share counts ("3 contracts"),
    or quoted-ticker prices since those don't appear in our brief format.
    """
    if _DOLLAR_RE.search(text):
        m = _DOLLAR_RE.search(text)
        raise LeakDetected(f"$-figure detected in public brief: {m.group(0)!r}")
    if _USD_NUMBER_RE.search(text):
        m = _USD_NUMBER_RE.search(text)
        raise LeakDetected(f"USD-prefixed amount in public brief: {m.group(0)!r}")
    if _NUMBER_USD_RE.search(text):
        m = _NUMBER_USD_RE.search(text)
        raise LeakDetected(f"amount-USD figure in public brief: {m.group(0)!r}")
    if _LEAK_TOKENS.search(text):
        m = _LEAK_TOKENS.search(text)
        raise LeakDetected(f"leak token in public brief: {m.group(0)!r}")
