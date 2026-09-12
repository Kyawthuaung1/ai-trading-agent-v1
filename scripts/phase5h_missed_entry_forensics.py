import json
from pathlib import Path

from trading_agent.mtf_fast import historical_mtf_events_fast
from trading_agent.backtest_mtf import deduplicate_candidates


DATA_DIR = Path("examples")
D1_FILE = DATA_DIR / "BTCUSDT_1d_3y.csv"
H4_FILE = DATA_DIR / "BTCUSDT_4h_3y.csv"

ENTRY_HORIZON = 30


def load_csv(path):
    import csv

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    return [
        {
            "timestamp": r["timestamp"],
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
        }
        for r in rows
    ]


def get_zone(candidate):
    ob = candidate["order_block"]
    low = float(ob["low"])
    high = float(ob["high"])

    if low > high:
        low, high = high, low

    return low, high


def classify_entry_path(candles, signal_index, direction, ob_low, ob_high):
    end = min(signal_index + ENTRY_HORIZON, len(candles) - 1)

    width = ob_high - ob_low

    if width <= 0:
        return {
            "classification": "INVALID_ZONE",
            "zone_touch": False,
            "midpoint_touch": False,
            "near_edge_touch": False,
            "shallow_touch": False,
        }

    midpoint = (ob_low + ob_high) / 2.0

    if direction == "bullish":
        shallow = ob_low + width * 0.25
        near_edge = ob_high
    else:
        shallow = ob_high - width * 0.25
        near_edge = ob_low

    zone_touch = False
    midpoint_touch = False
    shallow_touch = False
    near_edge_touch = False

    first_zone_index = None
    first_midpoint_index = None
    first_shallow_index = None
    first_near_edge_index = None

    for i in range(signal_index + 1, end + 1):
        candle = candles[i]
        lo = candle["low"]
        hi = candle["high"]

        if lo <= ob_high and hi >= ob_low:
            zone_touch = True
            if first_zone_index is None:
                first_zone_index = i

        if lo <= midpoint <= hi:
            midpoint_touch = True
            if first_midpoint_index is None:
                first_midpoint_index = i

        if lo <= shallow <= hi:
            shallow_touch = True
            if first_shallow_index is None:
                first_shallow_index = i

        if lo <= near_edge <= hi:
            near_edge_touch = True
            if first_near_edge_index is None:
                first_near_edge_index = i

    if near_edge_touch:
        classification = "NEAR_EDGE_REACHED"
    elif shallow_touch:
        classification = "SHALLOW_REACHED_ONLY"
    elif midpoint_touch:
        classification = "MIDPOINT_REACHED_ONLY"
    elif zone_touch:
        classification = "ZONE_TOUCHED_BUT_TARGETS_MISSED"
    else:
        classification = "ZONE_NOT_TOUCHED"

    return {
        "classification": classification,
        "zone_touch": zone_touch,
        "midpoint_touch": midpoint_touch,
        "near_edge_touch": near_edge_touch,
        "shallow_touch": shallow_touch,
        "first_zone_index": first_zone_index,
        "first_midpoint_index": first_midpoint_index,
        "first_shallow_index": first_shallow_index,
        "first_near_edge_index": first_near_edge_index,
    }


def main():
    d1 = load_csv(D1_FILE)
    h4 = load_csv(H4_FILE)

    raw_candidates = historical_mtf_events_fast(d1, h4)
    candidates = deduplicate_candidates(raw_candidates, min_gap=6)

    examples = []
    counts = {}

    for candidate in candidates:
        signal_index = int(candidate["index"])

        if signal_index >= len(h4) - 1:
            continue

        ob_low, ob_high = get_zone(candidate)

        result = classify_entry_path(
            h4,
            signal_index,
            candidate["direction"],
            ob_low,
            ob_high,
        )

        classification = result["classification"]
        counts[classification] = counts.get(classification, 0) + 1

        examples.append(
            {
                "index": signal_index,
                "timestamp": h4[signal_index]["timestamp"],
                "direction": candidate["direction"],
                "ob_low": ob_low,
                "ob_high": ob_high,
                **result,
            }
        )

    total = len(examples)

    summary = {
        "phase": "5H",
        "mission": "MISSED ENTRY FORENSICS",
        "dataset": {
            "d1_candles": len(d1),
            "h4_candles": len(h4),
            "start": h4[0]["timestamp"],
            "end": h4[-1]["timestamp"],
        },
        "parameters": {
            "entry_horizon_bars": ENTRY_HORIZON,
            "dedup_min_gap": 6,
        },
        "candidate_count": total,
        "classification_counts": counts,
        "classification_pct": {
            key: round(value * 100.0 / total, 4)
            for key, value in counts.items()
        },
        "research_note": (
            "Phase 5H is diagnostic only. It does not modify strategy "
            "parameters or create live-trading logic."
        ),
        "examples": examples,
    }

    Path("phase5h_results.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
