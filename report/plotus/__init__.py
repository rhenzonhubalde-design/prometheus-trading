"""
Plotus — public-facing Instagram content pipeline.

Daily + weekly briefs that Hermes (a separate content system) reads to
produce carousel posts. Hand-off contract:

    gdrive:AI Trading/Plotus/Briefs/{YYYY-MM-DD}/
        brief.md     — narrative for Hermes (third-person about "Plotus")
        data.json    — sanitized payload, percentages only, no $ figures

Entry points:
    python3 -m report.plotus.daily    — runs every day (incl. weekends)
    python3 -m report.plotus.weekly   — runs Sat 08:15 SGT
"""
