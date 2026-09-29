#!/usr/bin/env python3
"""Screen for low-float, high relative-volume movers and write data/latest.json.

Two passes:
  1. finviz screener for the float/relative-volume/% change criteria.
  2. yfinance per ticker, to get a real average-volume baseline and
     how far off today's high the price has slipped (the reversal signal).
"""
import json
import sys
from datetime import datetime, timezone

import yfinance as yf
from finvizfinance.screener.overview import Overview

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

    rows.sort(key=lambda r: (r["volRatio"] or 0), reverse=True)

    payload = {
        "scannedAt": datetime.now(timezone.utc).isoformat(),
        "criteria": FILTERS,
        "results": rows,
    }

    with open("data/latest.json", "w") as f:
        json.dump(payload, f, indent=2)

    print(f"Wrote {len(rows)} rows to data/latest.json")


if __name__ == "__main__":
    main()
