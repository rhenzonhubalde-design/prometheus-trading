# Hermes Contract — Plotus Instagram Content Pipeline

> Read this first. It tells the Hermes-side Claude session what Plotus produces,
> what Hermes is expected to produce, and the rules both sides must respect.

## 1. The two systems, one sentence each

- **Plotus** is an AI paper-trading system. Its trading desk lives in the
  `prometheus-trading` repo (internal codename: Prometheus) and runs on the
  Trading VPS. Every day, after computing its daily and weekly reports, it
  emits a **content brief** for Hermes to turn into an Instagram post.
- **Hermes** (you) is the content system. You read each brief from Google
  Drive, design an Instagram carousel, write the caption and hashtags, and
  publish to the `@plotus` Instagram account.

**Plotus is the public-facing brand name.** Never use "Prometheus" in
audience-facing content — that's the internal codebase name.

## 2. The hand-off contract

### Where briefs land

Plotus drops one folder per brief into Google Drive:

```
gdrive:AI Trading/Plotus/Briefs/{YYYY-MM-DD}/
    brief.md     ← narrative for you to base the post on
    data.json    ← structured numbers (percentages only)
```

Dates are in **SGT** (Singapore time, UTC+8) — that's the trading desk's
clock. A brief dated `2026-05-24` covers Friday 23 May US session activity.

### Cadence

| Brief type | Cron (SGT)       | Days                              | Window covered |
|------------|------------------|-----------------------------------|----------------|
| Daily      | `15 5 * * *`     | Every day (incl. weekends)        | The previous US session, or "the desk was dark" framing on weekends/holidays |
| Weekly     | `15 8 * * 6`     | Saturday only                     | Mon→Sun SGT of the most recently completed week |

You should poll Drive every morning at, say, 06:00 SGT for the daily, and
09:00 SGT on Saturdays for the weekly.

### `brief.md` — what's in it

2–4 short paragraphs of plain text. No headers, no bullets, no emoji,
no caption, no hashtags. The narrative is written in **third-person about
Plotus** ("Plotus opened AAPL today…", never "I", never "we"). Tone varies
by editorial angle (see §4).

You can use the brief verbatim as the seed for slide copy, OR rephrase it
to fit slide pacing — your call. The key rules in §3 are non-negotiable.

### `data.json` — schema reference

Every field is percentage-only or a safe identifier (ticker, direction,
conviction tier). Nothing is denominated in dollars. Schema below — fields
marked OPT may be absent on edge-case days.

```jsonc
{
  "date":   "2026-05-24",                    // SGT
  "type":   "daily" | "weekly",
  "angle":  "winning" | "losing" | "retrospective"
          | "milestone" | "quiet" | "reflective",
  "desk_active_today": true,                 // false on weekends/holidays — daily only

  // Open book (both daily + weekly)
  "open_count": 4,
  "open_positions": [
    {
      "ticker": "NVDA",
      "direction": "LONG",
      "conviction": "HIGH",
      "instrument": "stock",
      "unrealized_pct": -4.21,               // % vs entry
      "days_held": 3                         // weekly payload only
    }
  ],

  // Today's activity — daily only
  "trades_opened_today": 0,
  "trades_closed_today": 0,
  "opened_today":  [ { "ticker": "GOOG", "direction": "LONG", "conviction": "HIGH" } ],
  "closed_today":  [ { "ticker": "INTC", "direction": "LONG",
                       "pnl_pct": -1.2, "exit_reason": "stop hit" } ],
  "approved_today": 2,                       // count only, never names
  "rejected_today": 1,

  // Account exposure — all percentages of NetLiq
  "unrealized_pct_of_account":    0.417,
  "unrealized_pct_avg_position":  2.09,
  "budgeted_risk_pct_of_account": 0.836,
  "live_risk_pct_of_account":     1.953,
  "positions_missing_stop":       0,

  // Weekly-only fields (absent in daily payloads)
  "week_start": "2026-05-18",
  "week_end":   "2026-05-24",
  "opened_count": 3, "closed_count": 2,
  "win_count": 1, "loss_count": 1, "win_rate_pct": 50.0,
  "realized_pct_of_account": 0.25,
  "best_trade":  { "ticker": "AAPL", "direction": "LONG",
                   "pnl_pct": 4.0, "exit_reason": "target hit" },
  "worst_trade": { "ticker": "TSLA", "direction": "LONG",
                   "pnl_pct": -2.0, "exit_reason": "stop hit" },
  "open_count_eow": 2,

  // Context (both daily + weekly, may be absent if research data missing)
  "top_sectors": [
    { "ticker": "XLK", "name": "Technology" },
    { "ticker": "XLE", "name": "Energy" },
    { "ticker": "XLY", "name": "Consumer Discretionary" }
  ],
  "recent_win_rate_pct": 33.3,               // last 30d for daily, 90d for weekly
  "streak": { "kind": "win" | "loss", "length": 3 }
}
```

## 3. Brand voice — non-negotiable rules

These rules are enforced upstream and Hermes must respect them on the
publication side too.

### Voice

- **Third-person about Plotus.** "Plotus opened…", "Plotus is watching…".
  Never "I", never "we", never "the team".
- Plotus is framed as an autonomous AI paper-trading system documenting
  its experiment publicly.

### Privacy — percentages only

- **Never publish dollar amounts**, NetLiq, account size, entry/exit prices,
  share counts, or contract counts. If a number isn't a percentage, don't
  publish it.
- Tickers (`AAPL`, `XLK`), direction (`LONG` / `SHORT`), and conviction
  tier (`HIGH` / `MEDIUM` / `LOW`) are fine.
- The upstream sanitizer (`report/plotus/sanitizer.py`) refuses to ship
  any brief containing `$`, `USD`, `NetLiq`, or `account_value` tokens —
  if you ever see one in `brief.md`, that's a bug, report it.

### Content rules

- **No buy/sell recommendations.** Not "you should buy X." Plotus is
  documenting its own experiment, not advising anyone.
- **No hype.** No "MASSIVE", "🚀", "to the moon", etc.
- **No financial advice disclaimers needed in body** — the bio carries
  "Paper trading experiment. Not financial advice." Repeat in caption if
  comfortable.
- **No references to ITPM, Anton Kreil, or third-party methodologies.**
  Plotus has its own approach (call it "Plotus Method" if you need a
  label, but prefer not to brand the methodology at all).

### Content mix target (loose, not hard)

- ~80% **documentary** — what Plotus did, what's running, what closed,
  what was learned.
- ~20% **educational** — one principle explained with that day's real
  example (sector rotation, conviction tiering, risk sizing, options
  structures, etc.).

## 4. The six editorial angles

Plotus picks ONE angle per brief based on what actually happened. The
`angle` field in `data.json` tells you which one. Treat it as a tone
direction, not a template.

| Angle | When it fires | Slide pacing suggestion |
|-------|---------------|-------------------------|
| `winning` | Realized day/week clearly green, or unrealized >+0.5% of account | Lead with the result, then process. Stay humble — markets give and take. |
| `losing`  | Realized day/week clearly red, or unrealized <-0.5% of account | Frame as expected drawdown. Focus on discipline, stops holding, what the loss teaches. Never bravado, never excuses. |
| `retrospective` | A specific recent trade was meaningfully bad (worst `pnl_pct` ≤ -3% daily / -5% weekly) | Walk through the thesis vs what happened. Honest, specific, no spin. Good for educational hooks. |
| `milestone` | Trade count crosses a round number (10/25/50/100/…) OR streak ≥ 5 in a row | Mark the checkpoint without celebration. Look back at what's actually been learned. |
| `quiet` | No positions running AND no opens/closes/decisions | Don't fake activity. Talk about why patience is part of the strategy. What's on the radar without naming positions to take. |
| `reflective` | Default — routine day or non-trading day with positions running | Calm status update. Where positions stand, what Plotus is watching. Low drama. |

### Non-trading days (weekends, US holidays)

When `desk_active_today: false`:
- **Do not** claim Plotus reviewed or rejected setups today — the desk was dark.
- Frame the post as a quiet/reflective check-in on the existing book.
- The `recent_win_rate_pct` and `streak` fields are still meaningful
  (they're historical) — use them for context.

## 5. What Hermes should produce

For each daily brief:
- An Instagram **carousel** (typically 5–10 slides at 4:5 or 1:1).
- A **caption** that hooks in the first line, summarizes the post in
  2–4 short paragraphs, and ends with a question or quiet CTA
  ("What's on your radar this week?").
- A **hashtag block** appropriate to the angle and the day's tickers
  (e.g. `#trading #optionstrading #AITrading #papertrading $NVDA $AMD`).
- **Alt text** for each slide.

For each weekly brief: same structure, slightly longer carousel (7–10
slides), more retrospective angle. Use `best_trade` / `worst_trade` as
specific anchors.

### Slide structure — loose template (you decide the design)

| Slide | Daily | Weekly |
|-------|-------|--------|
| 1 | Hook — angle-driven headline | Hook — week-in-review headline |
| 2 | Today's activity (opens/closes) | Realized PnL %, win rate, opens/closes |
| 3 | Open book snapshot (ticker + unrealized %) | Best trade — ticker, %, exit reason |
| 4 | Risk exposure (% of account) | Worst trade — ticker, %, exit reason |
| 5 | Sectors / context | End-of-week open book |
| 6 | Reflection or educational beat | What Plotus is watching next week |
| ... | Variable | Variable |

### Captions — voice template

Match the body's third-person voice ("Plotus closed META today at +1.2%…").
Vary opening hooks by angle:

- `winning` — "When the setup plays out…"
- `losing`  — "Red prints are part of the experiment."
- `retrospective` — "One trade is worth a second look."
- `milestone` — "Quietly hitting checkpoint N."
- `quiet`   — "No new entries today. Plotus waits."
- `reflective` — "Where the book stands going into next week…"

Keep captions <2,200 chars (IG limit) but realistically <400 chars works
better.

## 6. Suggested Hermes implementation

You're free to design it however makes sense, but here's the shape we
discussed when designing the producer side:

1. **Drive watcher.** Poll `gdrive:AI Trading/Plotus/Briefs/` for new
   dated folders. Use rclone or the Google Drive API.
2. **Brief parser.** Load `brief.md` + `data.json`. Validate the schema
   (the fields above). Bail loudly if `$` ever appears in `brief.md` —
   that's an upstream bug.
3. **Slide planner.** Given the angle + data, choose 5–10 slide topics.
   The templates in §5 are a starting point, not a constraint.
4. **Slide renderer.** Generate the actual images (Canva API, PIL,
   Figma — your call). Keep design consistent across angles (one
   colourway per angle is a nice touch).
5. **Caption + hashtag writer.** Use Claude (or another LLM) with the
   voice rules from §3 baked into the system prompt.
6. **Publisher.** Push to Instagram via the Graph API (requires a
   Business/Creator account + Facebook Page).
7. **Audit log.** Save what was posted + when to a local DB so you can
   review what Plotus has said publicly. Useful for catching repetition
   or off-brand drift.

## 7. Things Hermes must NOT do

- ❌ Don't add dollar amounts, even if you "know" the account size from
  somewhere else.
- ❌ Don't speculate beyond what the brief says ("Plotus is bullish on AI
  long-term" — no, Plotus doesn't have opinions, it has data and trades).
- ❌ Don't give buy/sell recommendations or price targets.
- ❌ Don't use the codename "Prometheus" publicly.
- ❌ Don't post on a day where there's no fresh brief in Drive (= upstream
  cron failed; investigate, don't fabricate).
- ❌ Don't auto-respond to DMs or comments with anything other than a
  "this is a paper trading experiment, not financial advice" stock reply
  (or escalate to human).

## 8. Decision log — choices baked into this contract

Recorded so the next Claude understands the trade-offs and doesn't try to
relitigate them without a reason.

| Choice | What we picked | Why |
|--------|---------------|-----|
| Transport | Google Drive via rclone | Matches existing Plotus pattern + Hermes already pulls from Drive. |
| Format | `brief.md` (narrative) + `data.json` (numbers) | Hermes gets both editorial seed and raw data. Loose narrative — Hermes designs the slides, not Plotus. |
| Cadence | Daily every day + weekly Sat | Reflective posts on non-trading days keep the feed alive. |
| Privacy | Percentages only, no $ | Standard "journey of a bot" pattern. Account size stays private. |
| Voice | Third-person about Plotus | Frames the AI as a character. More journalistic than "we did X." |
| Caption | Hermes writes, not Plotus | Voice control on the content side. Plotus only produces the editorial seed. |
| Public brand | "Plotus" | Existing IG handle + Drive folder; internal codebase stays "Prometheus". |

## 9. Where the producer code lives

If you need to see what Plotus is actually emitting, the source is in
`report/plotus/` of the `prometheus-trading` repo:

```
report/plotus/
├── data.py        ← builds the publication-safe payload
├── sanitizer.py   ← enforces percentages-only rule
├── angles.py      ← picks one of the six angles
├── generator.py   ← writes brief.md via Claude
├── uploader.py    ← rclones the drop to Drive
├── daily.py       ← entry point (cron: 15 5 * * *)
└── weekly.py      ← entry point (cron: 15 8 * * 6)
```

If you find a contract bug (schema drift, $ leaking, broken angles),
open an issue against the `prometheus-trading` repo — don't paper over
it on the Hermes side.

---

**Last updated:** 2026-05-24
**Producer commit:** `216b8d6` (claude/daily-weekly-report-accuracy-qON8O)
