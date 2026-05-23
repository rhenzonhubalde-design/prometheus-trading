"""
Pick the editorial angle for a Plotus brief from what actually happened.

Six angles cover daily + weekly drops:
  winning        — meaningful realized + unrealized green; emphasise process
  losing         — meaningful red day/week; emphasise discipline, not bravado
  retrospective  — a recent loss to learn from publicly (only when the lesson is fresh)
  milestone      — a round-number event (50th trade, 100th, 10th win in a row, etc.)
  quiet          — no trades, no decisions, market closed or system idle
  reflective     — non-trading day with positions running, or routine update

The selector is intentionally simple: precedence-ordered triggers, first match wins.
Tested in report/tests/test_plotus_angles.py.
"""
from __future__ import annotations

from typing import Mapping, Optional


# Thresholds — kept here so they're easy to tune from tests.
WIN_PCT_THRESHOLD     = 0.5    # >+0.5% of account
LOSS_PCT_THRESHOLD    = -0.5   # <-0.5% of account
STREAK_MILESTONE_MIN  = 5      # 5+ in a row = milestone-worthy
TRADE_MILESTONES      = (10, 25, 50, 100, 250, 500, 1000)


def _meaningful_pct(value, threshold: float, *, positive: bool) -> bool:
    if value is None:
        return False
    v = float(value)
    return v >= threshold if positive else v <= threshold


def pick_daily_angle(payload: Mapping) -> str:
    """
    Daily angle precedence:
      milestone   (streak >= 5, or trade-count milestone via realized today)
      winning     (closed_today pnl avg >= +0.5% OR unrealized >= +0.5% of account)
      losing      (closed_today pnl avg <= -0.5% OR unrealized <= -0.5% of account)
      retrospective (any closed_today with pnl_pct <= -3% — a real lesson)
      quiet       (no positions running AND no opens/closes/decisions)
      reflective  (default fallback)
    """
    closed_today  = payload.get("closed_today") or []
    opened_today  = payload.get("opened_today") or []
    approved      = int(payload.get("approved_today") or 0)
    rejected      = int(payload.get("rejected_today") or 0)
    open_count    = int(payload.get("open_count") or 0)
    unreal_acct   = payload.get("unrealized_pct_of_account")
    streak        = payload.get("streak") or {}

    # 1. Milestone — winning streak length
    if streak.get("length", 0) >= STREAK_MILESTONE_MIN:
        return "milestone"

    # 2. Realized today summary
    closed_pcts = [float(c.get("pnl_pct") or 0) for c in closed_today]
    if closed_pcts:
        avg_closed = sum(closed_pcts) / len(closed_pcts)
        worst_closed = min(closed_pcts)
        if worst_closed <= -3.0:
            return "retrospective"
        if avg_closed >= 1.0:                # clearly green realized day
            return "winning"
        if avg_closed <= -1.0:               # clearly red realized day
            return "losing"

    # 3. Unrealized swing on positions
    if _meaningful_pct(unreal_acct, WIN_PCT_THRESHOLD, positive=True):
        return "winning"
    if _meaningful_pct(unreal_acct, LOSS_PCT_THRESHOLD, positive=False):
        return "losing"

    # 4. Truly quiet — nothing happened AND nothing's running
    if (not closed_today and not opened_today and approved == 0
            and rejected == 0 and open_count == 0):
        return "quiet"

    return "reflective"


def pick_weekly_angle(payload: Mapping) -> str:
    """
    Weekly angle precedence:
      milestone     (closed_count crosses a TRADE_MILESTONES boundary,
                     or streak >= 5)
      winning       (realized_pct_of_account >= +0.5%)
      losing        (realized_pct_of_account <= -0.5%)
      retrospective (worst trade pnl_pct <= -5%)
      quiet         (no opens, no closes, no positions)
      reflective    (default)
    """
    closed_count  = int(payload.get("closed_count") or 0)
    opened_count  = int(payload.get("opened_count") or 0)
    open_eow      = int(payload.get("open_count_eow") or 0)
    realized_pct  = payload.get("realized_pct_of_account")
    streak        = payload.get("streak") or {}
    worst         = payload.get("worst_trade") or {}

    if closed_count in TRADE_MILESTONES:
        return "milestone"
    if streak.get("length", 0) >= STREAK_MILESTONE_MIN:
        return "milestone"

    if _meaningful_pct(realized_pct, WIN_PCT_THRESHOLD, positive=True):
        return "winning"
    if _meaningful_pct(realized_pct, LOSS_PCT_THRESHOLD, positive=False):
        return "losing"

    worst_pct = worst.get("pnl_pct")
    if worst_pct is not None and float(worst_pct) <= -5.0:
        return "retrospective"

    if closed_count == 0 and opened_count == 0 and open_eow == 0:
        return "quiet"

    return "reflective"


def pick_angle(payload: Mapping) -> str:
    """Dispatch on payload['type']."""
    return (
        pick_weekly_angle(payload)
        if payload.get("type") == "weekly"
        else pick_daily_angle(payload)
    )
