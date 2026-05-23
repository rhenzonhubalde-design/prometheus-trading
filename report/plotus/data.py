"""
Build the publication-safe data payload for a Plotus brief.

Reads the v2 single-account state via report.positions_loader and the daily/weekly
stats via report.stats, then projects them into the percentages-only shape that
ships to Hermes. Nothing dollar-denominated leaves this module unless it has
been converted to % of NetLiq first.

`build_daily_payload`   — for python3 -m report.plotus.daily
`build_weekly_payload`  — for python3 -m report.plotus.weekly

Tests in report/tests/test_plotus_data.py.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, date, timedelta
from typing import Mapping, Optional, Sequence

from report import stats as _stats
from report.plotus.sanitizer import sanitize_payload


# Optional research-output paths. These are gitignored regen files written by
# the trading run; absent in dev / fresh checkouts. Brief degrades gracefully.
RESEARCH_DATA_DIR = os.path.expanduser('~/prometheus/trading/research/data')


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _load_optional_json(path: str, default):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return default
    return default


def _days_held(entry_date: Optional[str], reference: date) -> Optional[int]:
    d = _stats.parse_date(entry_date or "")
    return (reference - d).days if d else None


def _top_sectors(limit: int = 3) -> list[dict]:
    """Top sectors by composite score. Names + tickers only — no scores."""
    data = _load_optional_json(
        os.path.join(RESEARCH_DATA_DIR, 'sector_ranking.json'), {}
    )
    rows = (data.get('top_sectors') or [])[:limit]
    return [
        {"ticker": s.get("ticker"), "name": s.get("name")}
        for s in rows if s.get("ticker")
    ]


def _recent_win_rate(conn: Optional[sqlite3.Connection], days: int = 30) -> Optional[float]:
    """Recent win rate from SQLite history. None if unavailable."""
    if conn is None:
        return None
    end   = date.today()
    start = end - timedelta(days=days)
    try:
        rows = conn.execute(
            "SELECT pnl_pct FROM closed_trades WHERE exit_date >= ? AND exit_date <= ?",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    except sqlite3.DatabaseError:
        return None
    if not rows:
        return None
    wins = sum(1 for r in rows if float(r["pnl_pct"] or 0) > 0)
    return round(wins / len(rows) * 100.0, 1)


def _streak(conn: Optional[sqlite3.Connection], lookback: int = 10) -> Optional[dict]:
    """
    Look at the last `lookback` closed trades and return {kind, length}:
      kind   : 'win' | 'loss' | 'mixed'
      length : trailing run of same-sign trades from the most recent backwards
    None if SQLite is unavailable or no closed trades yet.
    """
    if conn is None:
        return None
    try:
        rows = conn.execute(
            "SELECT pnl_pct FROM closed_trades ORDER BY exit_date DESC LIMIT ?",
            (lookback,),
        ).fetchall()
    except sqlite3.DatabaseError:
        return None
    if not rows:
        return None
    signs = [1 if float(r["pnl_pct"] or 0) > 0 else -1 for r in rows]
    first = signs[0]
    length = 1
    for s in signs[1:]:
        if s == first:
            length += 1
        else:
            break
    return {"kind": "win" if first > 0 else "loss", "length": length}


# ────────────────────────────────────────────────────────────────────
# Daily payload
# ────────────────────────────────────────────────────────────────────

def build_daily_payload(
    daily_stats: Mapping,
    *,
    opened_today: Sequence[Mapping] = (),
    closed_today: Sequence[Mapping] = (),
    approved_today: Sequence[Mapping] = (),
    rejected_today: Sequence[Mapping] = (),
    conn: Optional[sqlite3.Connection] = None,
    today: Optional[date] = None,
) -> dict:
    """
    Project `compute_daily_stats(...)` output (plus today's activity)
    into the publication-safe daily payload.
    """
    today = today or _stats.today_sgt()

    open_positions = [
        {
            "ticker":         p.get("ticker"),
            "direction":      p.get("direction"),
            "conviction":     p.get("conviction"),
            "instrument":     p.get("instrument"),
            "unrealized_pct": p.get("unrealized_pct"),
        }
        for p in (daily_stats.get("positions") or [])
    ]

    closed_summary = [
        {
            "ticker":      p.get("ticker"),
            "direction":   p.get("direction"),
            "pnl_pct":     round(float(p.get("pnl_pct") or 0), 1),
            "exit_reason": (p.get("exit_reason") or "")[:120],
        }
        for p in closed_today
    ]
    opened_summary = [
        {
            "ticker":     p.get("ticker"),
            "direction":  p.get("direction"),
            "conviction": p.get("conviction"),
        }
        for p in opened_today
    ]

    raw = {
        "date":  today.isoformat(),
        "type":  "daily",
        "angle": None,                       # filled in by angles.pick_angle

        "open_count":              int(daily_stats.get("open_trades") or 0),
        "open_positions":          open_positions,

        "trades_opened_today":     len(opened_summary),
        "trades_closed_today":     len(closed_summary),
        "opened_today":            opened_summary,
        "closed_today":            closed_summary,
        "approved_today":          len(approved_today),
        "rejected_today":          len(rejected_today),

        "unrealized_pct_of_account":   daily_stats.get("unrealized_pct_of_account"),
        "unrealized_pct_avg_position": daily_stats.get("unrealized_pct_avg_position"),
        "budgeted_risk_pct_of_account": daily_stats.get("budgeted_risk_pct_of_account"),
        "live_risk_pct_of_account":     daily_stats.get("live_risk_pct_of_account"),
        "positions_missing_stop":       int(daily_stats.get("positions_missing_stop") or 0),

        "top_sectors":         _top_sectors(),
        "recent_win_rate_pct": _recent_win_rate(conn),
        "streak":              _streak(conn),
    }
    return sanitize_payload(raw)


# ────────────────────────────────────────────────────────────────────
# Weekly payload
# ────────────────────────────────────────────────────────────────────

def build_weekly_payload(
    weekly_stats: Mapping,
    *,
    conn: Optional[sqlite3.Connection] = None,
) -> dict:
    """
    Project `compute_weekly_stats(...)` output into the publication-safe
    weekly payload.
    """
    def _trade_view(t: Optional[Mapping]) -> Optional[dict]:
        if not t:
            return None
        return {
            "ticker":      t.get("ticker"),
            "direction":   t.get("direction"),
            "pnl_pct":     round(float(t.get("pnl_pct") or 0), 1),
            "exit_reason": (t.get("exit_reason") or "")[:120],
        }

    eow_open = [
        {
            "ticker":         p.get("ticker"),
            "direction":      p.get("direction"),
            "unrealized_pct": p.get("unrealized_pct"),
            "days_held":      p.get("days_held"),
        }
        for p in (weekly_stats.get("end_of_week_open") or [])
    ]

    raw = {
        "date":       weekly_stats.get("week_end"),
        "type":       "weekly",
        "angle":      None,                  # filled in by angles.pick_angle

        "week_start": weekly_stats.get("week_start"),
        "week_end":   weekly_stats.get("week_end"),

        "opened_count": int(weekly_stats.get("opened_count") or 0),
        "closed_count": int(weekly_stats.get("closed_count") or 0),
        "win_count":    int(weekly_stats.get("win_count") or 0),
        "loss_count":   int(weekly_stats.get("loss_count") or 0),
        "win_rate_pct": weekly_stats.get("win_rate_pct"),

        "realized_pct_of_account": weekly_stats.get("realized_pnl_pct_of_account"),

        "best_trade":  _trade_view(weekly_stats.get("best_trade")),
        "worst_trade": _trade_view(weekly_stats.get("worst_trade")),

        "open_count_eow":  int(weekly_stats.get("open_count_eow") or 0),
        "open_positions":  eow_open,

        "top_sectors":         _top_sectors(),
        "recent_win_rate_pct": _recent_win_rate(conn, days=90),
        "streak":              _streak(conn),
    }
    return sanitize_payload(raw)
