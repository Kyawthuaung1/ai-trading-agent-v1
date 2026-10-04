import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from trading_agent.backtest_mtf import (
    atr,
    deduplicate_candidates,
    simulate_trade,
)
from trading_agent.mtf_fast import historical_mtf_events_fast


ROOT = Path(__file__).resolve().parents[1]

D1_PATH = ROOT / "examples" / "BTCUSDT_1d_3y.csv"
H4_PATH = ROOT / "examples" / "BTCUSDT_4h_3y.csv"
OUT_PATH = ROOT / "phase5g_results.json"

STARTING_EQUITY = 10_000.0
RISK_PCT = 0.005
RR = 2.25
STOP_BUFFER_ATR = 0.25
FEE_RATE = 0.0004
SLIPPAGE_BPS = 2.0

INITIAL_TRAIN_MONTHS = 12
TEST_MONTHS = 6
ENTRY_HORIZON = 30
MIN_GAP = 6


def parse_dt(value):
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    dt = datetime.fromisoformat(value)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


def load_csv(path):
    rows = []

    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            rows.append(
                {
                    "timestamp": parse_dt(row["timestamp"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                }
            )

    return rows


def add_months(dt, months):
    year = dt.year + (dt.month - 1 + months) // 12
    month = (dt.month - 1 + months) % 12 + 1

    # All datasets used here are daily/hourly boundaries.
    # Clamp the day so month arithmetic remains deterministic.
    import calendar

    day = min(dt.day, calendar.monthrange(year, month)[1])

    return dt.replace(year=year, month=month, day=day)


def filter_strategy_candidates(candidates):
    selected = []

    for signal in candidates:
        direction = signal.get("direction")
        sweep = str(signal.get("sweep", "")).lower()

        if direction == "bearish" and "bull" in sweep:
            selected.append(signal)

        elif direction == "bullish" and "bear" in sweep:
            selected.append(signal)

    return deduplicate_candidates(selected, min_gap=MIN_GAP)


def zone_values(signal):
    ob = signal.get("order_block")

    if not ob:
        return None

    low = float(ob["low"])
    high = float(ob["high"])

    if high <= low:
        return None

    return low, high


def entry_price_for_model(signal, model):
    values = zone_values(signal)

    if values is None:
        return None

    low, high = values
    midpoint = (low + high) / 2.0
    width = high - low

    direction = signal["direction"]

    if model == "MIDPOINT":
        return midpoint

    if model == "NEAR_EDGE":
        if direction == "bullish":
            return high
        return low

    if model == "SHALLOW_RETRACE":
        # 25% inward from the near edge.
        if direction == "bullish":
            return high - (width * 0.25)

        return low + (width * 0.25)

    return None


def build_static_trade(signal, candles, model):
    entry = entry_price_for_model(signal, model)

    if entry is None:
        return None

    signal_index = int(signal["index"])

    if signal_index < 0 or signal_index >= len(candles):
        return None

    current_atr = atr(candles[: signal_index + 1])

    if current_atr <= 0:
        return None

    ob_low, ob_high = zone_values(signal)
    direction = signal["direction"]

    if direction == "bullish":
        stop = ob_low - (STOP_BUFFER_ATR * current_atr)
    else:
        stop = ob_high + (STOP_BUFFER_ATR * current_atr)

    risk = abs(entry - stop)

    if risk <= 0:
        return None

    if direction == "bullish":
        tp1 = entry + risk
        tp2 = entry + (risk * RR)
        tp3 = entry + (risk * 3.0)
    else:
        tp1 = entry - risk
        tp2 = entry - (risk * RR)
        tp3 = entry - (risk * 3.0)

    return {
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "risk": abs(entry - stop),
        "signal_index": signal_index,
    }


def candle_touches_zone(candle, low, high):
    return candle["low"] <= high and candle["high"] >= low


def find_static_touch(signal, candles, test_start, test_end, model):
    """
    Find the first valid entry touch inside the same OOS fold.

    This is diagnostic only. It never searches beyond test_end.
    """
    entry = entry_price_for_model(signal, model)

    if entry is None:
        return None

    signal_index = int(signal["index"])
    ob_low, ob_high = zone_values(signal)

    start = max(signal_index + 1, test_start)
    end = min(signal_index + 1 + ENTRY_HORIZON, test_end)

    if start >= end:
        return None

    for i in range(start, end):
        candle = candles[i]

        if candle["low"] <= entry <= candle["high"]:
            return {
                "trigger_index": i,
                "entry": entry,
                "zone_low": ob_low,
                "zone_high": ob_high,
            }

    return None


def find_structure_confirmation(signal, candles, test_start, test_end):
    """
    Conservative structure-confirmed re-entry.

    1. Price must first touch the original OB zone.
    2. A later/equal H4 candle must close directionally beyond
       the OB midpoint.
    3. Entry is the confirmation candle close.
    4. Simulation begins on the next candle.

    No future candle after the confirmation candle is used
    to determine the confirmation itself.
    """
    values = zone_values(signal)

    if values is None:
        return None

    ob_low, ob_high = values
    midpoint = (ob_low + ob_high) / 2.0
    direction = signal["direction"]

    signal_index = int(signal["index"])

    start = max(signal_index + 1, test_start)
    end = min(signal_index + 1 + ENTRY_HORIZON, test_end)

    if start >= end:
        return None

    touched = False

    for i in range(start, end):
        candle = candles[i]

        if not touched:
            if candle_touches_zone(candle, ob_low, ob_high):
                touched = True
            else:
                continue

        if direction == "bullish":
            confirmed = (
                candle["close"] > candle["open"]
                and candle["close"] > midpoint
            )
        else:
            confirmed = (
                candle["close"] < candle["open"]
                and candle["close"] < midpoint
            )

        if confirmed:
            return {
                "trigger_index": i,
                "entry": candle["close"],
                "zone_low": ob_low,
                "zone_high": ob_high,
            }

    return None


def build_trigger_trade(signal, candles, trigger, trigger_index):
    entry = float(trigger["entry"])
    direction = signal["direction"]

    current_atr = atr(candles[: trigger_index + 1])

    if current_atr <= 0:
        return None

    ob_low = float(trigger["zone_low"])
    ob_high = float(trigger["zone_high"])

    if direction == "bullish":
        stop = ob_low - (STOP_BUFFER_ATR * current_atr)
    else:
        stop = ob_high + (STOP_BUFFER_ATR * current_atr)

    risk = abs(entry - stop)

    if risk <= 0:
        return None

    if direction == "bullish":
        tp1 = entry + risk
        tp2 = entry + (risk * RR)
        tp3 = entry + (risk * 3.0)
    else:
        tp1 = entry - risk
        tp2 = entry - (risk * RR)
        tp3 = entry - (risk * 3.0)

    return {
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "risk": abs(entry - stop),
        "signal_index": trigger_index,
    }


def outcome_from_trade_result(result):
    if not result:
        return "UNKNOWN"

    return str(result.get("result", result.get("status", "UNKNOWN"))).upper()


def classify_static(signal, candles, test_start, test_end, model):
    touch = find_static_touch(
        signal,
        candles,
        test_start,
        test_end,
        model,
    )

    if touch is None:
        return {
            "classification": "NO_ENTRY",
            "reason": "ENTRY_NOT_TOUCHED",
            "trigger": None,
            "trade": None,
        }

    trade = build_static_trade(signal, candles, model)

    if trade is None:
        return {
            "classification": "INVALID_TRADE",
            "reason": "TRADE_BUILD_FAILED",
            "trigger": touch,
            "trade": None,
        }

    return {
        "classification": "TRIGGERED",
        "reason": "ENTRY_TOUCHED",
        "trigger": touch,
        "trade": trade,
    }


def classify_confirmation(signal, candles, test_start, test_end):
    trigger = find_structure_confirmation(
        signal,
        candles,
        test_start,
        test_end,
    )

    if trigger is None:
        return {
            "classification": "NO_ENTRY",
            "reason": "NO_STRUCTURE_CONFIRMATION",
            "trigger": None,
            "trade": None,
        }

    trade = build_trigger_trade(
        signal,
        candles,
        trigger,
        trigger["trigger_index"],
    )

    if trade is None:
        return {
            "classification": "INVALID_TRADE",
            "reason": "TRADE_BUILD_FAILED",
            "trigger": trigger,
            "trade": None,
        }

    # The confirmation candle is the trigger candle.
    # There must be at least one candle after it inside the test fold.
    if trigger["trigger_index"] + 1 >= test_end:
        return {
            "classification": "NO_ENTRY",
            "reason": "CONFIRMATION_AT_FOLD_END",
            "trigger": trigger,
            "trade": None,
        }

    return {
        "classification": "TRIGGERED",
        "reason": "STRUCTURE_CONFIRMED",
        "trigger": trigger,
        "trade": trade,
    }


def run_one(signal, candles, test_start, test_end, model):
    if model == "STRUCTURE_CONFIRM":
        return classify_confirmation(
            signal,
            candles,
            test_start,
            test_end,
        )

    return classify_static(
        signal,
        candles,
        test_start,
        test_end,
        model,
    )


def summarize_rows(rows):
    signals = len(rows)

    triggered = sum(
        1 for row in rows
        if row["classification"] == "TRIGGERED"
    )

    no_entry = sum(
        1 for row in rows
        if row["classification"] == "NO_ENTRY"
    )

    invalid = sum(
        1 for row in rows
        if row["classification"] == "INVALID_TRADE"
    )

    results = [
        row["result"]
        for row in rows
        if row.get("result") not in (None, "NO_ENTRY", "UNKNOWN")
    ]

    wins = sum(1 for r in results if r == "WIN")
    losses = sum(1 for r in results if r == "LOSS")
    partials = sum(1 for r in results if r == "PARTIAL")

    resolved = wins + losses + partials

    pnl = sum(
        float(row.get("pnl", 0.0))
        for row in rows
        if row.get("pnl") is not None
    )

    win_rate = (
        (wins / (wins + losses) * 100.0)
        if (wins + losses) > 0
        else 0.0
    )

    no_entry_pct = (
        (no_entry / signals * 100.0)
        if signals
        else 0.0
    )

    return {
        "signals": signals,
        "triggered": triggered,
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "partials": partials,
        "no_entries": no_entry,
        "invalid_trades": invalid,
        "no_entry_pct": no_entry_pct,
        "win_rate_pct": win_rate,
        "pnl": pnl,
    }


def run_fold(candidates, candles, test_start, test_end):
    models = [
        "MIDPOINT",
        "NEAR_EDGE",
        "SHALLOW_RETRACE",
        "STRUCTURE_CONFIRM",
    ]

    output = {}

    for model in models:
        rows = []

        for signal in candidates:
            idx = int(signal["index"])

            if idx < test_start or idx >= test_end:
                continue

            diagnostic = run_one(
                signal,
                candles,
                test_start,
                test_end,
                model,
            )

            result = None
            pnl = 0.0

            if diagnostic["trade"] is not None:
                trade = diagnostic["trade"]

                sim = simulate_trade(
                    candles,
                    trade,
                    starting_equity=STARTING_EQUITY,
                    risk_pct=RISK_PCT,
                    fee_rate=FEE_RATE,
                    slippage_bps=SLIPPAGE_BPS,
                    max_bars=ENTRY_HORIZON,
                )

                result = outcome_from_trade_result(sim)

                if isinstance(sim, dict):
                    pnl = float(sim.get("pnl", 0.0))

            rows.append(
                {
                    "signal_index": idx,
                    "classification": diagnostic["classification"],
                    "reason": diagnostic["reason"],
                    "result": result,
                    "pnl": pnl,
                    "trigger_index": (
                        diagnostic["trigger"]["trigger_index"]
                        if diagnostic["trigger"]
                        else None
                    ),
                }
            )

        output[model] = summarize_rows(rows)

    return output


def build_folds(candles):
    start = candles[0]["timestamp"]
    end = candles[-1]["timestamp"]

    train_start = start
    test_start = add_months(start, INITIAL_TRAIN_MONTHS)

    folds = []

    while test_start < end:
        test_end = min(add_months(test_start, TEST_MONTHS), end)

        if test_start >= test_end:
            break

        folds.append(
            {
                "train_start": train_start,
                "train_end": test_start,
                "test_start": test_start,
                "test_end": test_end,
            }
        )

        test_start = test_end

    return folds


def timestamp_index(candles):
    return [c["timestamp"] for c in candles]


def nearest_index(timestamps, dt):
    for i, ts in enumerate(timestamps):
        if ts >= dt:
            return i

    return len(timestamps)


def aggregate_fold_summaries(fold_summaries):
    output = {}

    models = [
        "MIDPOINT",
        "NEAR_EDGE",
        "SHALLOW_RETRACE",
        "STRUCTURE_CONFIRM",
    ]

    for model in models:
        summaries = [
            fold[model]
            for fold in fold_summaries
        ]

        signals = sum(x["signals"] for x in summaries)
        triggered = sum(x["triggered"] for x in summaries)
        resolved = sum(x["resolved"] for x in summaries)
        wins = sum(x["wins"] for x in summaries)
        losses = sum(x["losses"] for x in summaries)
        partials = sum(x["partials"] for x in summaries)
        no_entries = sum(x["no_entries"] for x in summaries)
        invalid = sum(x["invalid_trades"] for x in summaries)
        pnl = sum(x["pnl"] for x in summaries)

        output[model] = {
            "signals": signals,
            "triggered": triggered,
            "resolved": resolved,
            "wins": wins,
            "losses": losses,
            "partials": partials,
            "no_entries": no_entries,
            "invalid_trades": invalid,
            "no_entry_pct": (
                no_entries / signals * 100.0
                if signals
                else 0.0
            ),
            "win_rate_pct": (
                wins / (wins + losses) * 100.0
                if (wins + losses)
                else 0.0
            ),
            "pnl": pnl,
        }

    return output


def main():
    d1 = load_csv(D1_PATH)
    h4 = load_csv(H4_PATH)

    raw_candidates = historical_mtf_events_fast(d1, h4)
    candidates = filter_strategy_candidates(raw_candidates)

    timestamps = timestamp_index(h4)
    folds = build_folds(h4)

    fold_results = []

    for fold_number, fold in enumerate(folds, start=1):
        test_start_idx = nearest_index(
            timestamps,
            fold["test_start"],
        )

        test_end_idx = nearest_index(
            timestamps,
            fold["test_end"],
        )

        if test_start_idx >= test_end_idx:
            continue

        summaries = run_fold(
            candidates,
            h4,
            test_start_idx,
            test_end_idx,
        )

        fold_results.append(
            {
                "fold": fold_number,
                "train_start": fold["train_start"].isoformat(),
                "train_end": fold["train_end"].isoformat(),
                "test_start": fold["test_start"].isoformat(),
                "test_end": fold["test_end"].isoformat(),
                **summaries,
            }
        )

    aggregate = aggregate_fold_summaries(fold_results)

    # Dedicated missed-opportunity audit for the 5F baseline.
    baseline_rows = []

    for fold in fold_results:
        for model in ["NEAR_EDGE"]:
            # Reconstruct only the fold-level diagnostics.
            test_start_idx = nearest_index(
                timestamps,
                parse_dt(fold["test_start"]),
            )
            test_end_idx = nearest_index(
                timestamps,
                parse_dt(fold["test_end"]),
            )

            for signal in candidates:
                idx = int(signal["index"])

                if not (
                    test_start_idx <= idx < test_end_idx
                ):
                    continue

                diagnostic = run_one(
                    signal,
                    h4,
                    test_start_idx,
                    test_end_idx,
                    model,
                )

                baseline_rows.append(
                    {
                        "classification": diagnostic["classification"],
                        "reason": diagnostic["reason"],
                    }
                )

    breakdown = {}

    for row in baseline_rows:
        key = row["reason"]
        breakdown[key] = breakdown.get(key, 0) + 1

    result = {
        "phase": "5G",
        "strategy": "BEARISH + BULLISH SWEEP",
        "mission": "ENTRY EFFICIENCY / MISSED OPPORTUNITY LAB",
        "validation": "EXPANDING WALK-FORWARD DIAGNOSTICS",
        "dataset": {
            "d1_candles": len(d1),
            "h4_candles": len(h4),
            "start": h4[0]["timestamp"].isoformat(),
            "end": h4[-1]["timestamp"].isoformat(),
        },
        "parameters": {
            "starting_equity": STARTING_EQUITY,
            "risk_pct": RISK_PCT,
            "rr": RR,
            "stop_buffer_atr": STOP_BUFFER_ATR,
            "fee_rate": FEE_RATE,
            "slippage_bps": SLIPPAGE_BPS,
            "initial_train_months": INITIAL_TRAIN_MONTHS,
            "test_months": TEST_MONTHS,
            "entry_horizon_bars": ENTRY_HORIZON,
        },
        "candidate_count": len(candidates),
        "fold_count": len(fold_results),
        "full_walk_forward": aggregate,
        "folds": fold_results,
        "baseline_near_edge_missed_opportunity_breakdown": breakdown,
        "research_note": (
            "Phase 5G compares deterministic entry locations and a "
            "conservative structure-confirmed re-entry model. "
            "Each model is evaluated inside the same chronological "
            "walk-forward test folds. Entry searches are clipped to "
            "the OOS fold boundary to prevent cross-fold leakage. "
            "This is a research diagnostic, not live-trading logic."
        ),
    }

    OUT_PATH.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
