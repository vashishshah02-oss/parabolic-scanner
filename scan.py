#!/usr/bin/env python3
"""Screen for low-float, high relative-volume movers and write data/latest.json.

Two passes:
  1. finviz screener for the float/relative-volume/% change criteria.
  2. yfinance per ticker, to get a real average-volume baseline and
     how far off today's high the price has slipped (the reversal signal).
"""
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import yfinance as yf
from finvizfinance.screener.overview import Overview

HISTORY_PATH = "data/history.jsonl"

FILTERS = {
    "Float": "Under 50M",
    "Relative Volume": "Over 3",
    "Change": "Up 15%",
}


def screen_candidates():
    screener = Overview()
    screener.set_filter(filters_dict=FILTERS)
    df = screener.screener_view()
    if df is None or df.empty:
        return []
    return df.to_dict("records")


def enrich(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1mo", interval="1d")
        if hist.empty:
            return None
        avg_volume = float(hist["Volume"].mean())
        last = hist.iloc[-1]
        price = float(last["Close"])
        day_high = float(last["High"])
        day_low = float(last["Low"])
        volume = float(last["Volume"])

        # A zero average volume or a single-row/duplicated-bar history means
        # Yahoo has no real trading data for this name right now (commonly a
        # halted or barely-traded ticker serving a stale repeated bar) —
        # skip it rather than report a misleading "0% move, no volume" row.
        if not avg_volume or len(hist) < 2:
            return None

        prev_close = float(hist.iloc[-2]["Close"])
        if not prev_close:
            return None

        off_high_pct = ((price - day_high) / day_high) * 100 if day_high else 0.0
        vol_ratio = volume / avg_volume
        change_pct = ((price - prev_close) / prev_close) * 100

        return {
            "price": round(price, 4),
            "dayHigh": round(day_high, 4),
            "dayLow": round(day_low, 4),
            "volume": int(volume),
            "avgVolume": int(avg_volume),
            "volRatio": round(vol_ratio, 1),
            "offHighPct": round(off_high_pct, 1),
            "changePct": round(change_pct, 1),
        }
    except Exception as e:  # noqa: BLE001
        print(f"skip {ticker}: {e}", file=sys.stderr)
        return None


def stage_for(change_pct, off_high_pct):
    if change_pct is not None and change_pct < 0:
        return "faded"
    if off_high_pct <= -8:
        return "reversing"
    return "extended"


def load_flag_dates_by_ticker():
    """ticker -> set of flagDate strings this ticker has appeared on, from
    the history log written by every prior scan."""
    result = defaultdict(set)
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                e = json.loads(line)
                result[e["ticker"]].add(e["flagDate"])
    return result


def prev_weekday(d):
    d -= timedelta(days=1)
    while d.weekday() >= 5:  # Sat=5, Sun=6
        d -= timedelta(days=1)
    return d


def compute_day_streak(ticker, today, flag_dates_by_ticker):
    """How many consecutive trading days (including today) this ticker has
    shown up on the screen. Day 1 = first appearance, Day 2+ = a repeat
    performer — the distinction that matters for squeeze-fuel-remaining."""
    dates = flag_dates_by_ticker.get(ticker, set())
    streak = 1  # today's own appearance always counts
    d = prev_weekday(today)
    while d.isoformat() in dates:
        streak += 1
        d = prev_weekday(d)
    return streak


def log_new_signals(rows, scanned_at):
    """Append first-time-today sightings of each ticker to the history log.
    This is the dataset the backtest reads from — one row per (date, ticker),
    logged at the moment it was first flagged, not every rescan."""
    flag_date = datetime.fromisoformat(scanned_at).date().isoformat()
    seen_today = set()
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                e = json.loads(line)
                if e.get("flagDate") == flag_date:
                    seen_today.add(e["ticker"])

    new_entries = []
    for r in rows:
        if r["ticker"] in seen_today:
            continue
        entry = dict(r)
        entry["scannedAt"] = scanned_at
        entry["flagDate"] = flag_date
        new_entries.append(entry)
        seen_today.add(r["ticker"])

    if new_entries:
        with open(HISTORY_PATH, "a") as f:
            for e in new_entries:
                f.write(json.dumps(e) + "\n")
    print(f"Logged {len(new_entries)} new signals to {HISTORY_PATH}", file=sys.stderr)


def main():
    rows = []
    candidates = screen_candidates()
    print(f"finviz returned {len(candidates)} candidates", file=sys.stderr)

    for row in candidates:
        ticker = row.get("Ticker")
        if not ticker:
            continue
        detail = enrich(ticker)
        if not detail:
            continue
        rows.append({
            "ticker": ticker,
            "name": row.get("Company", ""),
            "sector": row.get("Sector", ""),
            **detail,
            "stage": stage_for(detail["changePct"], detail["offHighPct"]),
        })

    scanned_at = datetime.now(timezone.utc).isoformat()
    today = datetime.fromisoformat(scanned_at).date()
    flag_dates_by_ticker = load_flag_dates_by_ticker()
    for r in rows:
        r["dayStreak"] = compute_day_streak(r["ticker"], today, flag_dates_by_ticker)

    rows.sort(key=lambda r: (r["volRatio"] or 0), reverse=True)

    payload = {
        "scannedAt": scanned_at,
        "criteria": FILTERS,
        "results": rows,
    }

    with open("data/latest.json", "w") as f:
        json.dump(payload, f, indent=2)

    log_new_signals(rows, scanned_at)

    print(f"Wrote {len(rows)} rows to data/latest.json")


if __name__ == "__main__":
    main()
