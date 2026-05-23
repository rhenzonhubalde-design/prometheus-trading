"""Tests for the Plotus editorial-angle selector."""
import unittest

from report.plotus.angles import (
    pick_daily_angle, pick_weekly_angle, pick_angle,
)


def _daily(**overrides):
    base = {
        "type": "daily",
        "open_count": 0,
        "trades_opened_today": 0,
        "trades_closed_today": 0,
        "opened_today": [],
        "closed_today": [],
        "approved_today": 0,
        "rejected_today": 0,
        "unrealized_pct_of_account": 0.0,
        "streak": None,
    }
    base.update(overrides)
    return base


def _weekly(**overrides):
    base = {
        "type": "weekly",
        "opened_count": 0,
        "closed_count": 0,
        "open_count_eow": 0,
        "win_rate_pct": 0,
        "realized_pct_of_account": 0,
        "best_trade":  None,
        "worst_trade": None,
        "streak": None,
    }
    base.update(overrides)
    return base


class DailyAngleTests(unittest.TestCase):

    def test_quiet_when_nothing_happened(self):
        self.assertEqual(pick_daily_angle(_daily()), "quiet")

    def test_reflective_when_positions_running_but_no_decisions(self):
        # has open positions, no opens/closes/decisions today, mild unrealized
        p = _daily(open_count=3, unrealized_pct_of_account=0.1)
        self.assertEqual(pick_daily_angle(p), "reflective")

    def test_winning_on_realized_average(self):
        p = _daily(closed_today=[
            {"ticker": "AAPL", "pnl_pct": 3.2},
            {"ticker": "MSFT", "pnl_pct": 4.0},
        ])
        self.assertEqual(pick_daily_angle(p), "winning")

    def test_losing_on_realized_average(self):
        p = _daily(closed_today=[
            {"ticker": "TSLA", "pnl_pct": -2.0},
            {"ticker": "NVDA", "pnl_pct": -1.5},
        ])
        self.assertEqual(pick_daily_angle(p), "losing")

    def test_retrospective_on_a_real_loss(self):
        # avg might be near zero but one trade is meaningfully bad
        p = _daily(closed_today=[
            {"ticker": "META", "pnl_pct": +3.0},
            {"ticker": "AMD",  "pnl_pct": -4.0},
        ])
        self.assertEqual(pick_daily_angle(p), "retrospective")

    def test_winning_on_unrealized_when_no_closes(self):
        p = _daily(open_count=2, unrealized_pct_of_account=1.2)
        self.assertEqual(pick_daily_angle(p), "winning")

    def test_losing_on_unrealized_when_no_closes(self):
        p = _daily(open_count=2, unrealized_pct_of_account=-0.9)
        self.assertEqual(pick_daily_angle(p), "losing")

    def test_milestone_on_winning_streak(self):
        p = _daily(streak={"kind": "win", "length": 6})
        self.assertEqual(pick_daily_angle(p), "milestone")

    def test_streak_short_does_not_trigger_milestone(self):
        p = _daily(open_count=2, unrealized_pct_of_account=1.2,
                   streak={"kind": "win", "length": 3})
        self.assertEqual(pick_daily_angle(p), "winning")

    def test_decisions_but_no_trades_is_reflective_not_quiet(self):
        # approvals/rejections happened — still active behind the scenes
        p = _daily(approved_today=2, rejected_today=1)
        self.assertEqual(pick_daily_angle(p), "reflective")


class WeeklyAngleTests(unittest.TestCase):

    def test_quiet_when_nothing_at_all(self):
        self.assertEqual(pick_weekly_angle(_weekly()), "quiet")

    def test_winning_on_realized_pct(self):
        p = _weekly(closed_count=3, realized_pct_of_account=2.4)
        self.assertEqual(pick_weekly_angle(p), "winning")

    def test_losing_on_realized_pct(self):
        p = _weekly(closed_count=2, realized_pct_of_account=-1.2)
        self.assertEqual(pick_weekly_angle(p), "losing")

    def test_retrospective_on_a_big_loser(self):
        # realized near zero but the worst trade is brutal
        p = _weekly(
            closed_count=3,
            realized_pct_of_account=0.1,
            worst_trade={"ticker": "X", "pnl_pct": -7.5},
        )
        self.assertEqual(pick_weekly_angle(p), "retrospective")

    def test_milestone_on_trade_count_boundary(self):
        for n in (10, 25, 50, 100):
            with self.subTest(n=n):
                p = _weekly(closed_count=n, realized_pct_of_account=0.0)
                self.assertEqual(pick_weekly_angle(p), "milestone")

    def test_milestone_on_streak(self):
        p = _weekly(closed_count=4, streak={"kind": "win", "length": 5})
        self.assertEqual(pick_weekly_angle(p), "milestone")


class DispatchTests(unittest.TestCase):

    def test_pick_angle_dispatches_on_type(self):
        self.assertEqual(pick_angle({"type": "daily"}), "quiet")
        self.assertEqual(pick_angle({"type": "weekly"}), "quiet")
        # default: treat as daily
        self.assertEqual(pick_angle({}), "quiet")


if __name__ == "__main__":
    unittest.main()
