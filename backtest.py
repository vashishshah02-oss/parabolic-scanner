#!/usr/bin/env python3
"""Check whether the scanner's stage classification (Extended/Reversing/Faded)
actually predicts forward returns, using the signals logged in
data/history.jsonl. For each signal, looks up the close price 1/3/5 trading
days after it was flagged and computes the return from the flag-moment price.

Signals too recent to have 1/3/5 future trading days yet are marked pending
rather than guessed at — the whole point is not to fool ourselves.
"""
import json
import sys
from collections import defaultdict
from datetime import datetime

import yfinance as yf

HISTORY_PATH = "data/history.jsonl"
OUTPUT_PATH = "data/backtest.json"
HORIZONS = (1, 3, 5)


def load_history():
    signals = []
    with open(HISTORY_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                signals.append(json.loads(line))
    return signals


def forward_returns(ticker, flag_date_str, flag_price):
    """Returns {1: pct_or_None, 3: ..., 5: ...} plus 'pending' horizons."""
    t = yf.Ticker(ticker)
    hist = t.history(start=flag_date_str, period="3mo", interval="1d")
    if hist.empty:
        return {h: None for h in HORIZONS}, list(HORIZONS)

    flag_date = datetime.fromisoformat(flag_date_str).date()
    future = hist[hist.index.date > flag_date]

    results, pending = {}, []
    for h in HORIZONS:
        if len(future) >= h:
            close = float(future.iloc[h - 1]["Close"])
            results[h] = round(((close - flag_price) / flag_price) * 100, 2)
        else:
            results[h] = None
            pending.append(h)
    return results, pending


def main():
    try:
        signals = load_history()
    except FileNotFoundError:
        print("No history log yet — run scan.py a few times first.", file=sys.stderr)
        sys.exit(0)

    print(f"Backtesting {len(signals)} logged signals...", file=sys.stderr)

    enriched = []
    for sig in signals:
        rets, pending = forward_returns(sig["ticker"], sig["flagDate"], sig["price"])
        enriched.append({**sig, "returns": rets, "pending": pending})

    # Aggregate by stage x horizon, using only signals with a real (non-pending) reading.
    buckets = defaultdict(lambda: defaultdict(list))
    for e in enriched:
        for h in HORIZONS:
            r = e["returns"][h]
            if r is not None:
                buckets[e["stage"]][h].append(r)

    summary = {}
    for stage, by_horizon in buckets.items():
        summary[stage] = {}
        for h, values in by_horizon.items():
            summary[stage][f"t{h}"] = {
                "n": len(values),
                "avgReturnPct": round(sum(values) / len(values), 2),
                "pctNegative": round(100 * sum(1 for v in values if v < 0) / len(values), 1),
            }

    payload = {
        "generatedAt": datetime.now().isoformat(),
        "totalSignals": len(signals),
        "summary": summary,
        "signals": enriched,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"\nWrote {OUTPUT_PATH}\n")
    print(f"{'STAGE':<12}{'HORIZON':<10}{'N':<6}{'AVG RET':<10}{'% NEGATIVE'}")
    for stage, by_horizon in summary.items():
        for h_key, stats in sorted(by_horizon.items()):
            print(f"{stage:<12}{h_key:<10}{stats['n']:<6}{stats['avgReturnPct']:+.2f}%    {stats['pctNegative']}%")


if __name__ == "__main__":
    main()
