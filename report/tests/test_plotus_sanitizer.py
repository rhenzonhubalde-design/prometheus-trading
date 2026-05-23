"""Tests for the Plotus privacy sanitizer."""
import unittest

from report.plotus.sanitizer import (
    LeakDetected,
    sanitize_payload,
    sanitize_position,
    assert_no_dollar_leaks,
    PUBLIC_KEYS,
    POSITION_PUBLIC_KEYS,
)


class SanitizePayloadTests(unittest.TestCase):

    def test_keeps_public_keys(self):
        raw = {"date": "2026-05-23", "type": "daily", "angle": "winning"}
        self.assertEqual(sanitize_payload(raw), raw)

    def test_drops_unknown_non_leaky_keys_silently(self):
        out = sanitize_payload({
            "date": "2026-05-23",
            "type": "daily",
            "unknown_field": "ignore me",
        })
        self.assertNotIn("unknown_field", out)
        self.assertIn("date", out)

    def test_raises_on_dollar_keys(self):
        for leaky in ("total_unrealized_usd", "account_value", "entry_price",
                      "entry_size_usd", "pnl_usd", "current_price",
                      "calculated_stop", "risk_per_share"):
            with self.subTest(leaky=leaky):
                with self.assertRaises(LeakDetected):
                    sanitize_payload({"date": "x", leaky: 100})

    def test_strips_position_lists_to_safe_keys(self):
        out = sanitize_payload({
            "open_positions": [{
                "ticker":         "AAPL",
                "direction":      "LONG",
                "unrealized_pct": 1.2,
                "entry_price":    150.0,         # must be stripped
                "entry_size_usd": 5000,          # must be stripped
                "current_price":  152.0,         # must be stripped
            }],
        })
        self.assertEqual(len(out["open_positions"]), 1)
        pos = out["open_positions"][0]
        self.assertIn("ticker", pos)
        self.assertIn("unrealized_pct", pos)
        self.assertNotIn("entry_price", pos)
        self.assertNotIn("entry_size_usd", pos)
        self.assertNotIn("current_price", pos)

    def test_sanitize_position_drops_unknown_keys(self):
        p = {
            "ticker": "MSFT", "direction": "LONG", "pnl_pct": 3.1,
            "secret_account_id": "U1234567",
        }
        out = sanitize_position(p)
        self.assertEqual(out, {"ticker": "MSFT", "direction": "LONG", "pnl_pct": 3.1})

    def test_best_worst_trade_are_sanitized(self):
        out = sanitize_payload({
            "best_trade":  {"ticker": "NVDA", "pnl_pct": 12.0, "pnl_usd": 1200},
            "worst_trade": {"ticker": "INTC", "pnl_pct": -8.0, "entry_size_usd": 3000},
        })
        self.assertNotIn("pnl_usd",       out["best_trade"])
        self.assertNotIn("entry_size_usd", out["worst_trade"])
        self.assertEqual(out["best_trade"]["pnl_pct"], 12.0)


class AssertNoDollarLeaksTests(unittest.TestCase):

    def test_passes_clean_text(self):
        assert_no_dollar_leaks(
            "Plotus opened AAPL today, the position is currently +2.1% with a "
            "live risk of 0.8% of account."
        )

    def test_passes_share_counts(self):
        assert_no_dollar_leaks("Plotus is running 4 positions today.")

    def test_passes_percent_signs(self):
        assert_no_dollar_leaks("The position is +12.3% on entry. Stop holds.")

    def test_catches_dollar_figure(self):
        with self.assertRaises(LeakDetected):
            assert_no_dollar_leaks("Position size $5,000.")

    def test_catches_usd_prefix(self):
        with self.assertRaises(LeakDetected):
            assert_no_dollar_leaks("Realized USD 412.50 today.")

    def test_catches_usd_suffix(self):
        with self.assertRaises(LeakDetected):
            assert_no_dollar_leaks("Realized 412.50 USD today.")

    def test_catches_netliq_token(self):
        with self.assertRaises(LeakDetected):
            assert_no_dollar_leaks("NetLiq held steady this week.")

    def test_catches_account_value_token(self):
        with self.assertRaises(LeakDetected):
            assert_no_dollar_leaks("Account value crept up after Friday's close.")


class PublicKeysContractTests(unittest.TestCase):

    def test_public_keys_have_no_dollar_suffixes(self):
        for k in PUBLIC_KEYS:
            self.assertFalse(k.endswith("_usd"), f"$ key in PUBLIC_KEYS: {k}")
            self.assertNotIn("dollar", k.lower(), f"dollar key: {k}")
            self.assertNotIn("netliq",  k.lower(), f"netliq key: {k}")

    def test_position_keys_have_no_dollar_fields(self):
        for k in POSITION_PUBLIC_KEYS:
            self.assertFalse(k.endswith("_usd"))
            self.assertNotIn("price",  k.lower())


if __name__ == "__main__":
    unittest.main()
