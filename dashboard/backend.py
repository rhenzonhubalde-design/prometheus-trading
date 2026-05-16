"""
Prometheus Dashboard — Backend API
FastAPI server that reads trade JSON files and serves the dashboard.
Run with: uvicorn backend:app --host 0.0.0.0 --port 8080
"""
import json
import os
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Prometheus Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Paths ──────────────────────────────────────────────────────────────────
BASE          = os.path.expanduser("~/prometheus")
OPEN_POS      = f"{BASE}/phase3/data/open_positions.json"
CLOSED_POS    = f"{BASE}/phase3/data/closed_positions.json"
APPROVED      = f"{BASE}/phase3/data/approved_trades.json"
REJECTED      = f"{BASE}/phase3/data/rejected_trades.json"
THESES        = f"{BASE}/phase2/data/trade_theses.json"
SECTOR_RANK   = f"{BASE}/phase2/data/sector_ranking.json"


def load(path, default):
    try:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    return default


def safe_float(val, default=0.0):
    try:
        v = float(val)
        import math
        return default if math.isnan(v) else v
    except Exception:
        return default


# ── Metrics endpoint ───────────────────────────────────────────────────────
@app.get("/api/metrics")
def get_metrics():
    open_pos   = load(OPEN_POS, [])
    closed_pos = load(CLOSED_POS, [])
    approved   = load(APPROVED, {}).get("trades", [])
    rejected   = load(REJECTED, {}).get("trades", [])

    # P&L calculations
    total_pnl_pct  = sum(safe_float(p.get("pnl_pct")) for p in closed_pos)
    total_pnl_usd  = sum(
        safe_float(p.get("pnl_pct")) / 100 * safe_float(p.get("entry_size_usd"))
        for p in closed_pos
    )

    # Win rate
    wins   = [p for p in closed_pos if safe_float(p.get("pnl_pct")) > 0]
    losses = [p for p in closed_pos if safe_float(p.get("pnl_pct")) <= 0]
    win_rate = (len(wins) / len(closed_pos) * 100) if closed_pos else 0

    # Avg win / avg loss ratio
    avg_win  = (sum(safe_float(p.get("pnl_pct")) for p in wins)  / len(wins))  if wins   else 0
    avg_loss = (sum(abs(safe_float(p.get("pnl_pct"))) for p in losses) / len(losses)) if losses else 0
    win_loss_ratio = (avg_win / avg_loss) if avg_loss else 0

    # Max drawdown (simple approximation)
    pnls = [safe_float(p.get("pnl_pct")) for p in closed_pos]
    max_drawdown = abs(min(pnls)) if pnls else 0

    # Open exposure
    open_exposure = sum(safe_float(p.get("position_size_pct")) for p in open_pos)

    return {
        "total_pnl_pct":     round(total_pnl_pct, 2),
        "total_pnl_usd":     round(total_pnl_usd, 2),
        "win_rate":          round(win_rate, 1),
        "win_loss_ratio":    round(win_loss_ratio, 2),
        "max_drawdown":      round(max_drawdown, 1),
        "open_positions":    len(open_pos),
        "closed_positions":  len(closed_pos),
        "total_trades":      len(open_pos) + len(closed_pos),
        "approved_today":    len(approved),
        "rejected_today":    len(rejected),
        "open_exposure_pct": round(open_exposure, 1),
        "targets": {
            "win_rate":      50,
            "win_loss_ratio":1.5,
            "max_drawdown":  15,
        }
    }


# ── Open positions ─────────────────────────────────────────────────────────
@app.get("/api/positions/open")
def get_open_positions():
    positions = load(OPEN_POS, [])
    result = []
    for p in positions:
        entry_price = safe_float(p.get("entry_price"))
        result.append({
            "ticker":           p.get("ticker", ""),
            "direction":        p.get("direction", ""),
            "conviction":       p.get("conviction", ""),
            "sector":           p.get("sector", ""),
            "entry_date":       p.get("entry_date", ""),
            "entry_price":      entry_price,
            "entry_qty":        p.get("entry_qty", 0),
            "entry_size_usd":   safe_float(p.get("entry_size_usd")),
            "position_size_pct":safe_float(p.get("position_size_pct")),
            "deadline_date":    p.get("deadline_date", ""),
            "core_thesis":      p.get("core_thesis", ""),
            "catalyst":         p.get("catalyst", ""),
            "invalidation_conditions": p.get("invalidation_conditions", ""),
            "paper_trade":      p.get("paper_trade", True),
        })
    return result


# ── Closed positions ───────────────────────────────────────────────────────
@app.get("/api/positions/closed")
def get_closed_positions():
    positions = load(CLOSED_POS, [])
    result = []
    for p in sorted(positions, key=lambda x: x.get("exit_date", ""), reverse=True):
        pnl = safe_float(p.get("pnl_pct"))
        result.append({
            "ticker":       p.get("ticker", ""),
            "direction":    p.get("direction", ""),
            "conviction":   p.get("conviction", ""),
            "sector":       p.get("sector", ""),
            "entry_date":   p.get("entry_date", ""),
            "exit_date":    p.get("exit_date", ""),
            "entry_price":  safe_float(p.get("entry_price")),
            "exit_price":   safe_float(p.get("exit_price")),
            "pnl_pct":      round(pnl, 2),
            "pnl_usd":      round(safe_float(p.get("pnl_pct")) / 100 * safe_float(p.get("entry_size_usd")), 2),
            "exit_reason":  p.get("exit_reason", ""),
            "paper_trade":  p.get("paper_trade", True),
        })
    return result


# ── Activity feed ──────────────────────────────────────────────────────────
@app.get("/api/activity")
def get_activity():
    events = []
    closed = load(CLOSED_POS, [])
    open_p = load(OPEN_POS, [])
    rejected = load(REJECTED, {}).get("trades", [])

    for p in open_p:
        events.append({
            "type":    "opened",
            "ticker":  p.get("ticker"),
            "direction": p.get("direction"),
            "conviction": p.get("conviction"),
            "date":    p.get("entry_date"),
            "time":    p.get("entry_time", ""),
            "detail":  p.get("core_thesis", "")[:150],
            "size_pct": safe_float(p.get("position_size_pct")),
        })

    for p in closed:
        pnl = safe_float(p.get("pnl_pct"))
        events.append({
            "type":    "closed",
            "ticker":  p.get("ticker"),
            "direction": p.get("direction"),
            "date":    p.get("exit_date"),
            "time":    p.get("exit_time", ""),
            "pnl_pct": round(pnl, 2),
            "detail":  p.get("exit_reason", "")[:150],
        })

    for p in rejected:
        events.append({
            "type":    "rejected",
            "ticker":  p.get("ticker"),
            "direction": p.get("direction"),
            "date":    p.get("risk_check_time", "")[:10],
            "time":    p.get("risk_check_time", ""),
            "detail":  " | ".join(p.get("risk_checks", []))[:150],
        })

    events.sort(key=lambda x: x.get("time", ""), reverse=True)
    return events[:30]


# ── Sector rankings ────────────────────────────────────────────────────────
@app.get("/api/sectors")
def get_sectors():
    data = load(SECTOR_RANK, {})
    return {
        "generated_at": data.get("generated_at", ""),
        "sectors": data.get("all_sectors", []),
        "top":     data.get("top_sectors", []),
        "bottom":  data.get("bottom_sectors", []),
    }


# ── Risk exposure ──────────────────────────────────────────────────────────
@app.get("/api/risk")
def get_risk():
    open_pos = load(OPEN_POS, [])
    sector_exposure = {}
    for p in open_pos:
        sector = p.get("sector", "Unknown")
        key = sector.split("(")[0].strip() if "(" in sector else sector
        sector_exposure[key] = sector_exposure.get(key, 0) + safe_float(p.get("position_size_pct"))

    largest = max((safe_float(p.get("position_size_pct")) for p in open_pos), default=0)
    net_delta = sum(
        safe_float(p.get("position_size_pct")) * (1 if p.get("direction") == "LONG" else -1)
        for p in open_pos
    )

    return {
        "open_count":       len(open_pos),
        "largest_position": round(largest, 1),
        "net_delta":        round(abs(net_delta), 1),
        "sector_exposure":  {k: round(v, 1) for k, v in sector_exposure.items()},
        "limits": {
            "max_position":  5,
            "max_sector":    20,
            "max_positions": 5,
            "max_delta":     30,
        }
    }


# ── Performance chart data ─────────────────────────────────────────────────
@app.get("/api/performance")
def get_performance():
    closed = load(CLOSED_POS, [])
    closed_sorted = sorted(closed, key=lambda x: x.get("exit_date", ""))

    points = []
    cumulative = 0
    for p in closed_sorted:
        pnl = safe_float(p.get("pnl_pct"))
        cumulative += pnl
        points.append({
            "date": p.get("exit_date", ""),
            "pnl_pct": round(pnl, 2),
            "cumulative_pct": round(cumulative, 2),
        })
    return points


# ── Serve dashboard HTML ───────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_dashboard():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
