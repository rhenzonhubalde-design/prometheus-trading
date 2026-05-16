"""
Prometheus — Learning Engine
Reads the trade journal and generates a concise insight summary
that the Analysis Agent injects into its prompt when self_improving is ON.
"""
import json
import os
from datetime import datetime

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prometheus_config.json')


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def is_learning_enabled():
    config = load_json(CONFIG_PATH, {})
    return config.get('self_improving', False)


def get_learning_label():
    config = load_json(CONFIG_PATH, {})
    ab = config.get('ab_test', {})
    if config.get('self_improving'):
        return ab.get('learning_label', 'with_learning')
    return ab.get('baseline_label', 'no_learning')


def get_insights():
    """
    Build a concise insight block for the Analysis Agent prompt.
    Only called when self_improving is ON.
    Returns a formatted string or empty string if insufficient data.
    """
    config  = load_json(CONFIG_PATH, {})
    journal = load_json(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data/trade_journal.json'), []
    )
    stats   = load_json(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data/performance_stats.json'), {}
    )

    min_trades = config.get('learning', {}).get('min_trades_for_pattern', 2)
    max_patterns = config.get('learning', {}).get('max_patterns_to_inject', 5)
    lookback = config.get('learning', {}).get('lookback_trades', 20)

    if not journal:
        return ""

    recent = journal[-lookback:]
    if len(recent) < min_trades:
        return ""

    lines = ["\n=== HISTORICAL LEARNING INSIGHTS (self-improving mode ON) ==="]
    lines.append(f"Based on {len(recent)} reviewed trades:\n")

    # Conviction performance
    by_conv = stats.get('by_conviction', {})
    if by_conv:
        lines.append("CONVICTION PERFORMANCE:")
        for conv, data in sorted(by_conv.items(), key=lambda x: x[1].get('win_rate', 0), reverse=True):
            if data['trades'] >= min_trades:
                lines.append(
                    f"  {conv}: {data['trades']} trades | "
                    f"{data['win_rate']}% win rate | "
                    f"avg {data['avg_pnl']:+.1f}%"
                )

    # Best sectors
    by_sector = stats.get('by_sector', {})
    if by_sector:
        best = sorted(
            [(k, v) for k, v in by_sector.items() if v['trades'] >= min_trades],
            key=lambda x: x[1].get('avg_pnl', 0), reverse=True
        )[:3]
        if best:
            lines.append("\nBEST PERFORMING SECTORS HISTORICALLY:")
            for sector, data in best:
                lines.append(f"  {sector}: avg {data['avg_pnl']:+.1f}% | {data['win_rate']}% win rate")

    # Winning patterns
    winning = stats.get('winning_patterns', {})
    if winning:
        top_wins = sorted(winning.items(), key=lambda x: x[1], reverse=True)[:max_patterns]
        lines.append("\nPATTERNS THAT CORRELATE WITH WINS:")
        for tag, count in top_wins:
            lines.append(f"  {tag}: seen in {count} winning trade(s)")

    # Losing patterns to avoid
    losing = stats.get('losing_patterns', {})
    if losing:
        top_losses = sorted(losing.items(), key=lambda x: x[1], reverse=True)[:3]
        lines.append("\nPATTERNS TO AVOID (correlate with losses):")
        for tag, count in top_losses:
            lines.append(f"  {tag}: seen in {count} losing trade(s)")

    # Key lessons
    lessons = stats.get('top_lessons', [])[:3]
    if lessons:
        lines.append("\nKEY LESSONS FROM PAST TRADES:")
        for lesson in lessons:
            if lesson:
                lines.append(f"  - {lesson}")

    # Repeat setups
    repeats = stats.get('repeat_setups', [])[:3]
    if repeats:
        lines.append("\nSETUPS WORTH REPEATING:")
        for r in repeats:
            tags = ', '.join(r.get('tags', []))
            lines.append(f"  {r.get('ticker')} — {tags}")

    # A/B verdict
    ab = stats.get('ab_comparison', {})
    if ab and ab.get('verdict') != 'INCONCLUSIVE':
        lines.append(f"\nA/B TEST RESULT: {ab.get('verdict')}")
        lines.append(f"  Learning mode avg P&L: {ab.get('learning_avg_pnl',0):+.1f}%")
        lines.append(f"  Baseline avg P&L: {ab.get('baseline_avg_pnl',0):+.1f}%")

    lines.append("\nINSTRUCTION: Use these historical insights to refine your thesis quality.")
    lines.append("Weight conviction levels, sectors, and patterns that have proven profitable.")
    lines.append("Avoid patterns that correlate with losses. Apply lessons to new thesis generation.")
    lines.append("=== END LEARNING INSIGHTS ===\n")

    return '\n'.join(lines)


if __name__ == '__main__':
    enabled = is_learning_enabled()
    label   = get_learning_label()
    print(f"Learning mode: {'ON' if enabled else 'OFF'}")
    print(f"Trade label:   {label}")
    if enabled:
        insights = get_insights()
        print("\nInsights that would be injected:")
        print(insights or "(Not enough data yet — need more closed trades)")
