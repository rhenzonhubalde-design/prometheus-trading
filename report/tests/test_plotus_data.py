"""Tests for the Plotus data-payload builder."""
import json
import os
import tempfile
import unittest
from datetime import date

from report.plotus import data as plotus_data
from report.plotus.sanitizer import LeakDetected


def _daily_stats(**overrides):
    base = {
        "account":                      "A — BASELINE",
        "currency":                     "USD",
        "as_of":                        "2026-05-23T10:00:00+08:00",
        "open_trades":                  2,
        "priced_count":                 2,
        "account_value":                100000.0,
        "total_open_cost":              12000.0,
        "total_unrealized_usd":         420.0,
        "unrealized_pct_of_account":    0.42,
        "unrealized_pct_avg_position":  3.5,
        "budgeted_risk_usd":            500.0,
        "live_risk_usd":                350.0,
        "budgeted_risk_pct_of_account": 0.5,
        "live_risk_pct_of_account":     0.35,
        "positions_missing_stop":       0,
        "positions": [
            {
                "ticker": "AAPL", "direction": "LONG", "conviction": "high",
                "instrument": "stock",
                "entry_price": 150.0, "entry_size_usd": 6000.0,
                "unrealized_pct": 2.1, "unrealized_usd": 126.0,
                "current_price": 153.15,
            },
            {
                "ticker": "MSFT", "direction": "LONG", "conviction": "medium",
                "instrument": "stock",
                "entry_price": 400.0, "entry_size_usd": 6000.0,
                "unrealized_pct": 4.9, "unrealized_usd": 294.0,
                "current_price": 419.6,
            },
        ],
    }
    base.update(overrides)
    return base


def _weekly_stats(**overrides):
    base = {
        "account": "A — BASELINE", "currency": "USD",
        "week_start": "2026-05-18", "week_end": "2026-05-24",
        "opened_count": 3, "closed_count": 2,
        "win_count": 1, "loss_count": 1, "win_rate_pct": 50.0,
        "realized_pnl_usd": 250.0, "realized_pnl_pct_of_account": 0.25,
        "best_trade":  {"ticker": "AAPL", "direction": "LONG",
                        "pnl_pct": 4.0, "_pnl_usd": 240.0,
                        "entry_size_usd": 6000, "exit_reason": "target hit"},
        "worst_trade": {"ticker": "TSLA", "direction": "LONG",
                        "pnl_pct": -2.0, "_pnl_usd": -120.0,
                        "entry_size_usd": 6000, "exit_reason": "stop hit"},
        "open_count_eow": 2,
        "end_of_week_open": [
            {"ticker": "NVDA", "direction": "LONG", "entry_date": "2026-05-20",
             "entry_price": 900.0, "current_price": 950.0,
             "days_held": 4, "unrealized_pct": 5.5, "unrealized_usd": 330.0,
             "available": True},
        ],
    }
    base.update(overrides)
    return base


class BuildDailyPayloadTests(unittest.TestCase):

    def test_payload_has_no_dollar_keys(self):
        payload = plotus_data.build_daily_payload(_daily_stats())
        text = json.dumps(payload)
        self.assertNotIn("_usd",            text)
        self.assertNotIn("account_value",   text)
        self.assertNotIn("entry_price",     text)
        self.assertNotIn("entry_size",      text)
        self.assertNotIn("current_price",   text)
        self.assertNotIn("NetLiq",          text)

    def test_payload_keeps_percentages(self):
        payload = plotus_data.build_daily_payload(_daily_stats())
        self.assertEqual(payload["unrealized_pct_of_account"], 0.42)
        self.assertEqual(payload["unrealized_pct_avg_position"], 3.5)
        self.assertEqual(payload["live_risk_pct_of_account"], 0.35)

    def test_open_positions_stripped_to_safe_keys(self):
        payload = plotus_data.build_daily_payload(_daily_stats())
        self.assertEqual(len(payload["open_positions"]), 2)
        for pos in payload["open_positions"]:
            self.assertEqual(
                set(pos.keys()),
                {"ticker", "direction", "conviction", "instrument", "unrealized_pct"},
            )

    def test_records_today_activity(self):
        opened = [{"ticker": "GOOG", "direction": "LONG", "conviction": "high",
                   "entry_price": 175.0, "entry_size_usd": 5000}]
        closed = [{"ticker": "INTC", "direction": "LONG", "pnl_pct": -1.2,
                   "exit_reason": "stop hit", "entry_size_usd": 5000, "pnl_usd": -60}]
        payload = plotus_data.build_daily_payload(
            _daily_stats(), opened_today=opened, closed_today=closed,
        )
        self.assertEqual(payload["trades_opened_today"], 1)
        self.assertEqual(payload["trades_closed_today"], 1)
        # closed entry kept but $-fields stripped
        c = payload["closed_today"][0]
        self.assertEqual(c["ticker"], "INTC")
        self.assertEqual(c["pnl_pct"], -1.2)
        self.assertNotIn("entry_size_usd", c)
        self.assertNotIn("pnl_usd",         c)
        # opened entry similarly stripped
        o = payload["opened_today"][0]
        self.assertEqual(o["ticker"], "GOOG")
        self.assertNotIn("entry_price",    o)
        self.assertNotIn("entry_size_usd", o)

    def test_records_decision_counts_not_lists(self):
        # decisions arrive as lists; we publish counts only (the rejection reasons
        # may include sensitive ticker reasoning that hasn't been reviewed for IG).
        payload = plotus_data.build_daily_payload(
            _daily_stats(),
            approved_today=[{"ticker": "X"}, {"ticker": "Y"}],
            rejected_today=[{"ticker": "Z", "risk_checks": ["✗ secret reason"]}],
        )
        self.assertEqual(payload["approved_today"], 2)
        self.assertEqual(payload["rejected_today"], 1)

    def test_date_defaults_to_today_sgt(self):
        payload = plotus_data.build_daily_payload(_daily_stats())
        # 2026-05-23 is the fixed test date (CLAUDE.md context); we don't pin
        # the value, just check it's an ISO date.
        self.assertRegex(payload["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(payload["type"], "daily")

    def test_date_can_be_overridden(self):
        payload = plotus_data.build_daily_payload(_daily_stats(),
                                                  today=date(2026, 1, 1))
        self.assertEqual(payload["date"], "2026-01-01")


class BuildWeeklyPayloadTests(unittest.TestCase):

    def test_payload_has_no_dollar_keys(self):
        payload = plotus_data.build_weekly_payload(_weekly_stats())
        text = json.dumps(payload)
        self.assertNotIn("_usd",          text)
        self.assertNotIn("realized_pnl_usd", text)
        self.assertNotIn("entry_price",   text)

    def test_keeps_percentages_and_counts(self):
        payload = plotus_data.build_weekly_payload(_weekly_stats())
        self.assertEqual(payload["type"], "weekly")
        self.assertEqual(payload["win_rate_pct"], 50.0)
        self.assertEqual(payload["realized_pct_of_account"], 0.25)
        self.assertEqual(payload["opened_count"], 3)
        self.assertEqual(payload["closed_count"], 2)

    def test_best_worst_trade_sanitized(self):
        payload = plotus_data.build_weekly_payload(_weekly_stats())
        self.assertNotIn("_pnl_usd",       payload["best_trade"])
        self.assertNotIn("entry_size_usd", payload["best_trade"])
        self.assertEqual(payload["best_trade"]["pnl_pct"], 4.0)
        self.assertEqual(payload["worst_trade"]["pnl_pct"], -2.0)

    def test_eow_positions_sanitized(self):
        payload = plotus_data.build_weekly_payload(_weekly_stats())
        pos = payload["open_positions"][0]
        self.assertEqual(set(pos.keys()),
                         {"ticker", "direction", "unrealized_pct", "days_held"})
        self.assertEqual(pos["unrealized_pct"], 5.5)
        self.assertEqual(pos["days_held"], 4)

    def test_handles_no_trades_week(self):
        empty = _weekly_stats(closed_count=0, win_count=0, loss_count=0,
                              best_trade=None, worst_trade=None,
                              realized_pnl_pct_of_account=0.0,
                              end_of_week_open=[], open_count_eow=0)
        payload = plotus_data.build_weekly_payload(empty)
        self.assertEqual(payload["closed_count"], 0)
        self.assertIsNone(payload["best_trade"])
        self.assertIsNone(payload["worst_trade"])


class DeskActiveTodayTests(unittest.TestCase):

    def test_defaults_to_true_when_no_data_dir(self):
        # No data_dir → can't check freshness → assume desk was active.
        payload = plotus_data.build_daily_payload(_daily_stats())
        self.assertTrue(payload["desk_active_today"])

    def test_false_when_approved_file_missing(self):
        with tempfile.TemporaryDirectory() as d:
            payload = plotus_data.build_daily_payload(
                _daily_stats(), data_dir=d,
            )
            self.assertFalse(payload["desk_active_today"])

    def test_true_when_approved_file_mtime_is_today(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "approved_trades.json"), "w") as f:
                f.write("{}")
            # Note: file just created → mtime == now → today
            payload = plotus_data.build_daily_payload(
                _daily_stats(), data_dir=d,
            )
            self.assertTrue(payload["desk_active_today"])

    def test_false_when_approved_file_is_stale(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "approved_trades.json")
            with open(path, "w") as f:
                f.write("{}")
            # Backdate by 3 days
            old = os.path.getmtime(path) - 3 * 86400
            os.utime(path, (old, old))
            payload = plotus_data.build_daily_payload(
                _daily_stats(), data_dir=d,
            )
            self.assertFalse(payload["desk_active_today"])

    def test_stale_data_zeroes_approved_rejected_counts(self):
        # Critical regression: don't surface Friday's risk-gate output as today's.
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "approved_trades.json")
            with open(path, "w") as f:
                f.write("{}")
            old = os.path.getmtime(path) - 3 * 86400
            os.utime(path, (old, old))
            payload = plotus_data.build_daily_payload(
                _daily_stats(),
                approved_today=[{"ticker": "X"}, {"ticker": "Y"}],
                rejected_today=[{"ticker": "Z"}, {"ticker": "W"}, {"ticker": "V"}],
                data_dir=d,
            )
            self.assertFalse(payload["desk_active_today"])
            self.assertEqual(payload["approved_today"], 0)
            self.assertEqual(payload["rejected_today"], 0)


class LeakRefusalTests(unittest.TestCase):

    def test_payload_passes_sanitizer_round_trip(self):
        # Sanity: built payload must already be sanitized — re-running the
        # sanitizer on it must succeed (idempotent).
        from report.plotus.sanitizer import sanitize_payload
        payload = plotus_data.build_daily_payload(_daily_stats())
        sanitize_payload(payload)


if __name__ == "__main__":
    unittest.main()
