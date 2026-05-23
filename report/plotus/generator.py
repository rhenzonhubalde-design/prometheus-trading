"""
Plotus brief generator — turns a sanitized payload into a narrative `brief.md`.

The brief is Hermes's input. It's:
  - third-person about Plotus ("Plotus opened AAPL…", never "we" / "I")
  - percentages only, no $ figures (sanitizer enforces this)
  - 2-4 short paragraphs of narrative — no slide breakdown, no captions,
    no hashtags; Hermes handles slide design + caption writing
  - tone varies by angle (winning / losing / retrospective / milestone /
    quiet / reflective)

If ANTHROPIC_API_KEY is missing or the API call fails, falls back to a
deterministic template so the cron still produces a publishable file.

Tested via the daily/weekly entry-point integration tests; the prompt
construction logic itself is small enough not to need its own suite.
"""
from __future__ import annotations

import json
import os
from typing import Mapping

from report.plotus.sanitizer import assert_no_dollar_leaks


_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1500


_VOICE_RULES = """\
Voice + style rules — non-negotiable:
- Third-person about "Plotus". Never "I", never "we", never "the team".
- Plotus is an AI trading system documenting its paper-trading experiment.
- Percentages only. NEVER mention dollar amounts, NetLiq, account size,
  entry prices, or share counts. If a number isn't a percentage, don't
  publish it. (Tickers + direction LONG/SHORT are fine.)
- No hype, no buy/sell recommendations, no financial advice.
- Plain text. No markdown headers, no bullet symbols, no emoji.
- 2-4 short paragraphs. Aim for 120-220 words total.
- Do not write a caption or hashtags. Hermes handles that downstream.
- Never reference ITPM, Anton Kreil, or third-party methodologies.
- desk_active_today indicates whether Plotus's trading pipeline actually ran
  today (true on US trading days when the cron fires; false on weekends,
  US market holidays, and days the run didn't fire). When false: do NOT
  mention setups being filtered, approved, or rejected today — the desk
  was dark. Frame the day as a quiet/non-trading session and focus on
  the existing book."""


_ANGLE_GUIDES = {
    "winning": (
        "Today (or this week) went well. Frame it as process working as designed, "
        "not as a victory lap. Acknowledge what setup or signal was responsible. "
        "Stay humble — markets give and take."
    ),
    "losing": (
        "Today (or this week) was red. Frame it as part of the experiment — "
        "expected drawdowns, discipline holding stops, what the loss teaches. "
        "Never excuses, never bravado."
    ),
    "retrospective": (
        "A recent trade went meaningfully wrong. Walk through what the thesis was, "
        "what the market did instead, and what Plotus took from it. Honest, "
        "specific, no spin."
    ),
    "milestone": (
        "A counting milestone (streak length, trade count, or anniversary). "
        "Mark it as a checkpoint in the experiment, with a sober look at what's "
        "actually been learned so far."
    ),
    "quiet": (
        "No trades today (or this week). Reflective post about the system "
        "waiting for setups, why patience is part of the strategy, what's on "
        "the radar without naming positions to take."
    ),
    "reflective": (
        "Routine day or non-trading day. Brief status of where positions stand "
        "and what Plotus is watching. Calm, factual, low drama."
    ),
}


def _build_prompt(payload: Mapping) -> str:
    angle = payload.get("angle") or "reflective"
    guide = _ANGLE_GUIDES.get(angle, _ANGLE_GUIDES["reflective"])
    kind  = payload.get("type", "daily")

    facts = json.dumps(payload, indent=2, default=str)

    return f"""\
You are writing the Instagram content brief for Plotus, an AI trading system
documenting its paper-trading experiment publicly.

This is a {kind.upper()} brief, angle: {angle.upper()}.

{_VOICE_RULES}

Editorial angle guidance:
{guide}

Here is the publication-safe data for this brief (percentages only):
{facts}

Write the narrative now. 2-4 short paragraphs. No headers, no bullets, no
captions, no hashtags. Plain text only."""


def _fallback_narrative(payload: Mapping) -> str:
    """
    Used when the Claude API isn't available. Pure-template; the prose
    is intentionally generic so it can ship without review.
    """
    angle = payload.get("angle") or "reflective"
    kind  = payload.get("type", "daily")
    date  = payload.get("date", "")

    if kind == "weekly":
        opened = int(payload.get("opened_count") or 0)
        closed = int(payload.get("closed_count") or 0)
        wr     = payload.get("win_rate_pct")
        wr_str = f"{wr:.1f}% win rate" if wr is not None else "the week"
        line1 = (
            f"Plotus closed the week of {date}. The system opened {opened} new "
            f"positions and exited {closed}, marking {wr_str}."
        )
    else:
        opened = int(payload.get("trades_opened_today") or 0)
        closed = int(payload.get("trades_closed_today") or 0)
        open_n = int(payload.get("open_count") or 0)
        line1 = (
            f"Plotus logged {opened} new entries and {closed} exits on {date}, "
            f"with {open_n} positions still running."
        )

    framing = {
        "winning": "The session worked as designed — discipline held, the setup played out.",
        "losing":  "Red prints are part of the experiment. Stops held; the process continues.",
        "retrospective": "One trade is worth a second look — the thesis didn't hold.",
        "milestone": "A counting checkpoint in the experiment. Not a victory lap, just a marker.",
        "quiet":   "No fresh trades today. Plotus waits for setups rather than forcing entries.",
        "reflective": "A routine update — positions running, signals being watched.",
    }[angle]

    return f"{line1}\n\n{framing}"


def generate_brief(payload: Mapping) -> str:
    """
    Produce the narrative brief.md content. Calls Claude if ANTHROPIC_API_KEY
    is set; falls back to a template otherwise. Always asserts no $ leaks
    before returning.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    text: str

    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                messages=[{"role": "user", "content": _build_prompt(payload)}],
            )
            text = msg.content[0].text.strip()
            print(f"  [plotus] Claude narrative generated ({len(text)} chars)")
        except Exception as e:
            print(f"  [plotus] Claude call failed, falling back to template: {e}")
            text = _fallback_narrative(payload)
    else:
        print("  [plotus] ANTHROPIC_API_KEY not set — using template fallback "
              "(check ~/prometheus/.env loaded)")
        text = _fallback_narrative(payload)

    assert_no_dollar_leaks(text)
    return text
