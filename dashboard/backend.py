"""
Prometheus Dashboard — Backend API (v2 — A/B aware)
FastAPI server that reads from account_a/ and account_b/ data directories.
Run with: uvicorn backend:app --host 0.0.0.0 --port 8080
"""
import json
import os
import math
import time
from datetime import datetime
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

# ── Paths ───────────────────────────────────────────────────────────────────
BASE    = os.path.expanduser("~/prometheus")
ACCT_A  = os.path.join(BASE, "account_a", "data")
ACCT_B  = os.path.join(BASE, "account_b", "data")
PHASE2  = os.path.join(BASE, "phase2",    "data")


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
        return default if math.isnan(v) else v
    except Exception:
        return default


def load_account(data_dir, account_label):
    """Load all data for one account, tagging each position with account label."""
    open_pos    = load(os.path.join(data_dir, "open_positions.json"),    [])
    closed_pos  = load(os.path.join(data_dir, "closed_positions.json"),  [])
    approved    = load(os.path.join(data_dir, "approved_trades.json"),   {}).get("trades", [])
    rejected    = load(os.path.join(data_dir, "rejected_trades.json"),   {}).get("trades", [])
    journal     = load(os.path.join(data_dir, "trade_journal.json"),     [])
    perf_stats  = load(os.path.join(data_dir, "performance_stats.json"), {})

    # Tag every record with its account
    for p in open_pos:   p.setdefault("_account", account_label)
    for p in closed_pos: p.setdefault("_account", account_label)
    for p in approved:   p.setdefault("_account", account_label)
    for p in rejected:   p.setdefault("_account", account_label)

    return dict(open=open_pos, closed=closed_pos, approved=approved,
                rejected=rejected, journal=journal, perf_stats=perf_stats)


def account_stats(closed):
    """Quick win-rate / avg-pnl for one account's closed trades."""
    if not closed:
        return {"trades": 0, "win_rate": 0.0, "avg_pnl": 0.0, "total_pnl": 0.0}
    wins    = [p for p in closed if safe_float(p.get("pnl_pct")) > 0]
    avg_pnl = sum(safe_float(p.get("pnl_pct")) for p in closed) / len(closed)
    tot_pnl = sum(safe_float(p.get("pnl_pct")) / 100 * safe_float(p.get("entry_size_usd")) for p in closed)
    return {
        "trades":    len(closed),
        "win_rate":  round(len(wins) / len(closed) * 100, 1),
        "avg_pnl":   round(avg_pnl, 2),
        "total_pnl": round(tot_pnl, 2),
    }


# ── /api/metrics ────────────────────────────────────────────────────────────
@app.get("/api/metrics")
def get_metrics():
    a = load_account(ACCT_A, "A")
    b = load_account(ACCT_B, "B")

    all_closed  = a["closed"] + b["closed"]
    all_open    = a["open"]   + b["open"]
    all_approved= a["approved"] + b["approved"]
    all_rejected= a["rejected"] + b["rejected"]

    total_pnl_pct = sum(safe_float(p.get("pnl_pct")) for p in all_closed)
    total_pnl_usd = sum(
        safe_float(p.get("pnl_pct")) / 100 * safe_float(p.get("entry_size_usd"))
        for p in all_closed
    )
    wins   = [p for p in all_closed if safe_float(p.get("pnl_pct")) > 0]
    losses = [p for p in all_closed if safe_float(p.get("pnl_pct")) <= 0]
    win_rate     = (len(wins) / len(all_closed) * 100) if all_closed else 0
    avg_win      = (sum(safe_float(p.get("pnl_pct")) for p in wins)  / len(wins))  if wins   else 0
    avg_loss     = (sum(abs(safe_float(p.get("pnl_pct"))) for p in losses) / len(losses)) if losses else 0
    win_loss_ratio = (avg_win / avg_loss) if avg_loss else 0
    pnls         = [safe_float(p.get("pnl_pct")) for p in all_closed]
    max_drawdown = abs(min(pnls)) if pnls else 0
    open_exposure= sum(safe_float(p.get("position_size_pct")) for p in all_open)

    stats_a = account_stats(a["closed"])
    stats_b = account_stats(b["closed"])

    return {
        "total_pnl_pct":     round(total_pnl_pct, 2),
        "total_pnl_usd":     round(total_pnl_usd, 2),
        "win_rate":          round(win_rate, 1),
        "win_loss_ratio":    round(win_loss_ratio, 2),
        "max_drawdown":      round(max_drawdown, 1),
        "open_positions":    len(all_open),
        "closed_positions":  len(all_closed),
        "total_trades":      len(all_open) + len(all_closed),
        "approved_today":    len(all_approved),
        "rejected_today":    len(all_rejected),
        "open_exposure_pct": round(open_exposure, 1),
        "account_a":         stats_a,
        "account_b":         stats_b,
        "targets": {
            "win_rate":       50,
            "win_loss_ratio": 1.5,
            "max_drawdown":   15,
        },
    }


# ── /api/positions/open ──────────────────────────────────────────────────────
@app.get("/api/positions/open")
def get_open_positions():
    a = load_account(ACCT_A, "A")
    b = load_account(ACCT_B, "B")
    result = []
    for p in a["open"] + b["open"]:
        result.append({
            "ticker":            p.get("ticker", ""),
            "direction":         p.get("direction", ""),
            "conviction":        p.get("conviction", ""),
            "sector":            p.get("sector", ""),
            "entry_date":        p.get("entry_date", ""),
            "entry_price":       safe_float(p.get("entry_price")),
            "entry_qty":         p.get("entry_qty", 0),
            "entry_size_usd":    safe_float(p.get("entry_size_usd")),
            "position_size_pct": safe_float(p.get("position_size_pct")),
            "deadline_date":     p.get("deadline_date", ""),
            "core_thesis":       p.get("core_thesis", ""),
            "catalyst":          p.get("catalyst", ""),
            "invalidation_conditions": p.get("invalidation_conditions", ""),
            "calculated_stop":   p.get("calculated_stop"),
            "paper_trade":       p.get("paper_trade", True),
            "account":           p.get("_account", "?"),
            "learning_mode":     p.get("learning_mode", ""),
        })
    return result


# ── /api/positions/closed ────────────────────────────────────────────────────
@app.get("/api/positions/closed")
def get_closed_positions():
    a = load_account(ACCT_A, "A")
    b = load_account(ACCT_B, "B")
    positions = sorted(a["closed"] + b["closed"],
                       key=lambda x: x.get("exit_date", ""), reverse=True)
    result = []
    for p in positions:
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
            "pnl_usd":      round(pnl / 100 * safe_float(p.get("entry_size_usd")), 2),
            "exit_reason":  p.get("exit_reason", ""),
            "exit_category":p.get("exit_category", ""),
            "account":      p.get("_account", "?"),
            "learning_mode":p.get("learning_mode", ""),
            "paper_trade":  p.get("paper_trade", True),
        })
    return result


# ── /api/activity ─────────────────────────────────────────────────────────
@app.get("/api/activity")
def get_activity():
    a = load_account(ACCT_A, "A")
    b = load_account(ACCT_B, "B")
    events = []

    for p in a["open"] + b["open"]:
        events.append({
            "type":       "opened",
            "ticker":     p.get("ticker"),
            "direction":  p.get("direction"),
            "conviction": p.get("conviction"),
            "date":       p.get("entry_date"),
            "time":       p.get("entry_time", ""),
            "detail":     (p.get("core_thesis", "") or "")[:150],
            "size_pct":   safe_float(p.get("position_size_pct")),
            "account":    p.get("_account", "?"),
        })

    for p in a["closed"] + b["closed"]:
        events.append({
            "type":      "closed",
            "ticker":    p.get("ticker"),
            "direction": p.get("direction"),
            "date":      p.get("exit_date"),
            "time":      p.get("exit_time", ""),
            "pnl_pct":   round(safe_float(p.get("pnl_pct")), 2),
            "detail":    (p.get("exit_reason", "") or "")[:150],
            "account":   p.get("_account", "?"),
        })

    for p in a["rejected"] + b["rejected"]:
        events.append({
            "type":      "rejected",
            "ticker":    p.get("ticker"),
            "direction": p.get("direction"),
            "date":      (p.get("risk_check_time") or "")[:10],
            "time":      p.get("risk_check_time", ""),
            "detail":    " | ".join(p.get("risk_checks", []))[:150],
            "account":   p.get("_account", "?"),
        })

    events.sort(key=lambda x: x.get("time", ""), reverse=True)
    return events[:30]


# ── /api/sectors ───────────────────────────────────────────────────────────
@app.get("/api/sectors")
def get_sectors():
    data = load(os.path.join(PHASE2, "sector_ranking.json"), {})
    return {
        "generated_at": data.get("generated_at", ""),
        "sectors":      data.get("all_sectors", []),
        "top":          data.get("top_sectors", []),
        "bottom":       data.get("bottom_sectors", []),
    }


# ── /api/risk ──────────────────────────────────────────────────────────────
@app.get("/api/risk")
def get_risk():
    a = load_account(ACCT_A, "A")
    b = load_account(ACCT_B, "B")

    def calc_risk(open_pos, label):
        sector_exp = {}
        for p in open_pos:
            sector = p.get("sector", "Unknown")
            key    = sector.split("(")[0].strip() if "(" in sector else sector
            sector_exp[key] = sector_exp.get(key, 0) + safe_float(p.get("position_size_pct"))
        largest  = max((safe_float(p.get("position_size_pct")) for p in open_pos), default=0)
        net_delta = sum(
            safe_float(p.get("position_size_pct")) * (1 if p.get("direction") == "LONG" else -1)
            for p in open_pos
        )
        return {
            "label":          label,
            "open_count":     len(open_pos),
            "largest_position": round(largest, 1),
            "net_delta":      round(abs(net_delta), 1),
            "sector_exposure": {k: round(v, 1) for k, v in sector_exp.items()},
        }

    all_open = a["open"] + b["open"]
    return {
        "combined":  calc_risk(all_open,    "Combined"),
        "account_a": calc_risk(a["open"],   "Account A — Baseline"),
        "account_b": calc_risk(b["open"],   "Account B — Learning"),
        "limits": {
            "max_position":  5,
            "max_sector":   20,
            "max_positions": 5,
            "max_delta":    30,
        },
    }


# ── /api/performance ────────────────────────────────────────────────────────
@app.get("/api/performance")
def get_performance():
    a = load_account(ACCT_A, "A")
    b = load_account(ACCT_B, "B")

    def build_curve(closed, label):
        points, cum = [], 0
        for p in sorted(closed, key=lambda x: x.get("exit_date", "")):
            pnl  = safe_float(p.get("pnl_pct"))
            cum += pnl
            points.append({
                "date":           p.get("exit_date", ""),
                "pnl_pct":        round(pnl, 2),
                "cumulative_pct": round(cum, 2),
                "ticker":         p.get("ticker", ""),
                "account":        label,
            })
        return points

    return {
        "account_a": build_curve(a["closed"], "A"),
        "account_b": build_curve(b["closed"], "B"),
        "combined":  build_curve(a["closed"] + b["closed"], "Combined"),
    }


# ── /api/ab ─────────────────────────────────────────────────────────────────
@app.get("/api/ab")
def get_ab():
    a = load_account(ACCT_A, "A")
    b = load_account(ACCT_B, "B")
    stats_a = account_stats(a["closed"])
    stats_b = account_stats(b["closed"])

    delta_wr  = round(stats_b["win_rate"] - stats_a["win_rate"], 1)
    delta_pnl = round(stats_b["avg_pnl"]  - stats_a["avg_pnl"],  2)

    if len(a["closed"]) + len(b["closed"]) == 0:
        verdict = "NO_DATA"
    elif abs(delta_wr) <= 2:
        verdict = "INCONCLUSIVE"
    elif delta_wr > 2:
        verdict = "LEARNING_BETTER"
    else:
        verdict = "BASELINE_BETTER"

    return {
        "account_a":   {**stats_a, "open": len(a["open"]),   "label": "Baseline (No Learning)"},
        "account_b":   {**stats_b, "open": len(b["open"]),   "label": "Self-Improving (Learning ON)"},
        "delta_win_rate": delta_wr,
        "delta_avg_pnl":  delta_pnl,
        "verdict":         verdict,
        "min_trades_for_verdict": 10,
        "data_sufficient": (len(a["closed"]) >= 5 and len(b["closed"]) >= 5),
    }


# ── /api/pnl  (live floating P&L from IBKR) ─────────────────────────────────
@app.get("/api/pnl")
def get_pnl():
    """Fetch live floating P&L — runs IBKR fetch in a subprocess to avoid event loop conflicts."""
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, os.path.join(BASE, "dashboard", "pnl_worker.py")],
        capture_output=True, text=True, timeout=90
    )
    if result.returncode != 0:
        return {"error": result.stderr[:500], "positions": [], "total_pnl_usd": 0,
                "total_pnl_pct": 0, "priced_count": 0, "total_count": 0,
                "fetched_at": datetime.now().isoformat()}
    import json as _json
    return _json.loads(result.stdout)


def _fetch_pnl_blocking():
    try:
        from ib_insync import IB, Stock
    except ImportError:
        return {"error": "ib_insync not installed", "positions": []}

    a = load_account(ACCT_A, "A")
    b = load_account(ACCT_B, "B")

    results = []

    def fetch_prices(open_pos, port, account_label, client_id):
        if not open_pos:
            return
        ib = IB()
        connected = False
        try:
            ib.connect("127.0.0.1", port, clientId=client_id, timeout=10)
            ib.reqMarketDataType(4)   # delayed, free tier
            connected = True

            for p in open_pos:
                ticker     = p.get("ticker", "")
                direction  = p.get("direction", "LONG")
                entry_px   = safe_float(p.get("entry_price"))
                qty        = int(p.get("entry_qty", 0))
                size_usd   = safe_float(p.get("entry_size_usd"))
                stop       = p.get("calculated_stop")

                current = None
                source  = None
                try:
                    contract = Stock(ticker, "SMART", "USD")
                    ib.qualifyContracts(contract)
                    td = ib.reqMktData(contract, "", False, False)
                    ib.sleep(3)
                    for attr in ["last", "close", "bid"]:
                        v = getattr(td, attr, None)
                        if v and not math.isnan(v) and v > 0:
                            current = round(float(v), 2)
                            source  = attr
                            break
                except Exception:
                    pass

                if current and entry_px:
                    raw_pnl_pct = (current - entry_px) / entry_px * 100
                    if direction == "SHORT":
                        raw_pnl_pct = -raw_pnl_pct
                    pnl_pct = round(raw_pnl_pct, 2)
                    pnl_usd = round(raw_pnl_pct / 100 * size_usd, 2)
                    dist_to_stop = None
                    if stop:
                        stop_f = safe_float(stop)
                        dist_to_stop = round(abs(current - stop_f) / current * 100, 2)
                else:
                    pnl_pct = None
                    pnl_usd = None
                    dist_to_stop = None

                results.append({
                    "ticker":        ticker,
                    "account":       account_label,
                    "direction":     direction,
                    "conviction":    p.get("conviction", ""),
                    "sector":        p.get("sector", ""),
                    "entry_price":   entry_px,
                    "current_price": current,
                    "price_source":  source,
                    "qty":           qty,
                    "size_usd":      size_usd,
                    "pnl_pct":       pnl_pct,
                    "pnl_usd":       pnl_usd,
                    "calculated_stop": safe_float(stop) if stop else None,
                    "dist_to_stop_pct": dist_to_stop,
                    "entry_date":    p.get("entry_date", ""),
                    "deadline_date": p.get("deadline_date", ""),
                    "available":     current is not None,
                })
        except Exception as e:
            # Gateway unreachable — mark all positions as unavailable
            for p in open_pos:
                results.append({
                    "ticker":        p.get("ticker", ""),
                    "account":       account_label,
                    "direction":     p.get("direction", "LONG"),
                    "conviction":    p.get("conviction", ""),
                    "sector":        p.get("sector", ""),
                    "entry_price":   safe_float(p.get("entry_price")),
                    "current_price": None,
                    "price_source":  None,
                    "qty":           int(p.get("entry_qty", 0)),
                    "size_usd":      safe_float(p.get("entry_size_usd")),
                    "pnl_pct":       None,
                    "pnl_usd":       None,
                    "calculated_stop": None,
                    "dist_to_stop_pct": None,
                    "entry_date":    p.get("entry_date", ""),
                    "deadline_date": p.get("deadline_date", ""),
                    "available":     False,
                    "error":         str(e) or "Gateway unreachable",
                })
        finally:
            if connected:
                try: ib.disconnect()
                except: pass

    fetch_prices(a["open"], 4002, "A", 20)
    time.sleep(2)   # brief pause between gateways
    fetch_prices(b["open"], 4003, "B", 21)

    # Summary
    priced   = [r for r in results if r["available"]]
    total_pnl_usd = round(sum(r["pnl_usd"] or 0 for r in priced), 2)
    total_pnl_pct = round(sum(r["pnl_pct"] or 0 for r in priced), 2)

    return {
        "positions":      results,
        "total_pnl_usd":  total_pnl_usd,
        "total_pnl_pct":  total_pnl_pct,
        "priced_count":   len(priced),
        "total_count":    len(results),
        "fetched_at":     datetime.now().isoformat(),
    }


# ── Serve dashboard ──────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_dashboard():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
