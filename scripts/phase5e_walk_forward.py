import csv
import json
from datetime import datetime
from pathlib import Path

from trading_agent.backtest_mtf import (
    atr,
    deduplicate_candidates,
    simulate_trade,
)
from trading_agent.mtf_fast import historical_mtf_events_fast


DATA_DIR = Path("examples")
D1_FILE = DATA_DIR / "BTCUSDT_1d_3y.csv"
H4_FILE = DATA_DIR / "BTCUSDT_4h_3y.csv"

STARTING_EQUITY = 10000.0
RISK_PCT = 0.005
MIN_RR = 2.25
FEE_RATE = 0.0004
SLIPPAGE_BPS = 2.0

INITIAL_TRAIN_MONTHS = 12
TEST_MONTHS = 6


def load_csv(path):
    rows = []

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "timestamp": row.get("timestamp")
                or row.get("time")
                or row.get("datetime"),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })

    return rows


def parse_dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def add_months(dt, months):
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1

    day = min(
        dt.day,
        [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30,
         31, 31, 30, 31, 30, 31][month - 1],
    )

    return dt.replace(year=year, month=month, day=day)


def filter_strategy_candidates(candidates):
    selected = []

    for signal in candidates:
        direction = signal.get("direction")

        sweep = str(
            signal.get("sweep")
            or signal.get("liquidity_sweep")
            or ""
        ).lower()

        if direction == "bearish" and "bull" in sweep:
            selected.append(signal)

        elif direction == "bullish" and "bear" in sweep:
            selected.append(signal)

    return deduplicate_candidates(selected, min_gap=6)


def build_b_trade(signal, candles):
    ob = signal.get("order_block")

    if not ob:
        return None

    index = signal["index"]

    if index >= len(candles) - 1:
        return None

    direction = signal["direction"]

    # B = OB first-touch / near-edge entry.
    if direction == "bullish":
        entry = ob["high"]
    else:
        entry = ob["low"]

    a = atr(candles[:index + 1])

    if a <= 0:
        a = abs(ob["high"] - ob["low"])

    if a <= 0:
        return None

    if direction == "bullish":
        stop = ob["low"] - a * 0.25
        risk = entry - stop

        if risk <= 0:
            return None

        tp1 = entry + risk
        tp2 = entry + risk * MIN_RR
        tp3 = entry + risk * 3.0

    else:
        stop = ob["high"] + a * 0.25
        risk = stop - entry

        if risk <= 0:
            return None

        tp1 = entry - risk
        tp2 = entry - risk * MIN_RR
        tp3 = entry - risk * 3.0

    return {
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "risk": risk,
        "signal_index": index,
    }


def evaluate_fold(candidates, candles, test_start, test_end):
    selected = []

    for signal in candidates:
        idx = signal["index"]

        if idx < 0 or idx >= len(candles):
            continue

        ts = parse_dt(candles[idx]["timestamp"])

        if test_start <= ts < test_end:
            selected.append(signal)

    trades = []

    for signal in selected:
        trade = build_b_trade(signal, candles)

        if trade is not None:
            trades.append(trade)

    trades.sort(key=lambda x: x["signal_index"])

    # Re-deduplicate after trade construction.
    unique = []
    last_index = -999999

    for trade in trades:
        if trade["signal_index"] - last_index < 6:
            continue

        unique.append(trade)
        last_index = trade["signal_index"]

    # IMPORTANT:
    # Clip candles at the test-window boundary.
    # This prevents a trade from using future candles beyond OOS.
    clipped = [
        c for c in candles
        if parse_dt(c["timestamp"]) < test_end
    ]

    equity = STARTING_EQUITY
    wins = 0
    losses = 0
    partials = 0
    no_entries = 0
    resolved = 0
    total_pnl = 0.0

    peak = equity
    max_dd = 0.0

    profit = 0.0
    loss_abs = 0.0
    r_values = []

    for trade in unique:
        result = simulate_trade(
            clipped,
            trade,
            starting_equity=equity,
            risk_pct=RISK_PCT,
            fee_rate=FEE_RATE,
            slippage_bps=SLIPPAGE_BPS,
        )

        if result is None:
            continue

        outcome = str(result.get("result", "")).upper()

        pnl = float(
            result.get("pnl")
            or result.get("net_pnl")
            or 0.0
        )

        if outcome in ("NO_ENTRY", "NO ENTRY"):
            no_entries += 1
            continue

        total_pnl += pnl
        equity += pnl

        if pnl > 0:
            profit += pnl
        elif pnl < 0:
            loss_abs += abs(pnl)

        if outcome in ("WIN", "TP3", "FULL_WIN"):
            wins += 1
            resolved += 1
        elif outcome in ("LOSS", "SL"):
            losses += 1
            resolved += 1
        elif outcome in ("PARTIAL", "PARTIAL_WIN", "BE"):
            partials += 1
            resolved += 1

        risk_cash = STARTING_EQUITY * RISK_PCT
        r_values.append(pnl / risk_cash)

        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    pf = profit / loss_abs if loss_abs > 0 else None

    expectancy_r = (
        sum(r_values) / len(r_values)
        if r_values
        else 0.0
    )

    return {
        "test_start": test_start.isoformat(),
        "test_end": test_end.isoformat(),
        "signals": len(selected),
        "unique_trades": len(unique),
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "partials": partials,
        "no_entries": no_entries,
        "win_rate_pct": (
            wins / resolved * 100.0
            if resolved
            else 0.0
        ),
        "profit_factor": pf,
        "expectancy_r": expectancy_r,
        "pnl": total_pnl,
        "return_pct": total_pnl / STARTING_EQUITY * 100.0,
        "max_drawdown": max_dd,
    }


def build_folds(h4):
    start = parse_dt(h4[0]["timestamp"])
    end = parse_dt(h4[-1]["timestamp"])

    train_start = start
    test_start = add_months(train_start, INITIAL_TRAIN_MONTHS)

    folds = []

    while test_start < end:
        test_end = add_months(test_start, TEST_MONTHS)

        if test_end > end:
            test_end = end

        if test_end <= test_start:
            break

        folds.append({
            "train_start": train_start,
            "train_end": test_start,
            "test_start": test_start,
            "test_end": test_end,
        })

        # Expanding walk-forward:
        # training window remains anchored at dataset start.
        test_start = add_months(test_start, TEST_MONTHS)

    return folds


def main():
    d1 = load_csv(D1_FILE)
    h4 = load_csv(H4_FILE)

    all_candidates = historical_mtf_events_fast(d1, h4)
    candidates = filter_strategy_candidates(all_candidates)

    folds = build_folds(h4)

    results = []

    for fold in folds:
        result = evaluate_fold(
            candidates,
            h4,
            fold["test_start"],
            fold["test_end"],
        )

        result["train_start"] = fold["train_start"].isoformat()
        result["train_end"] = fold["train_end"].isoformat()

        results.append(result)

    resolved = sum(x["resolved"] for x in results)
    wins = sum(x["wins"] for x in results)
    losses = sum(x["losses"] for x in results)
    partials = sum(x["partials"] for x in results)
    no_entries = sum(x["no_entries"] for x in results)
    total_pnl = sum(x["pnl"] for x in results)

    positive_folds = sum(
        1 for x in results
        if x["expectancy_r"] > 0
    )

    profitable_folds = sum(
        1 for x in results
        if x["pnl"] > 0
    )

    fold_pf_values = [
        x["profit_factor"]
        for x in results
        if x["profit_factor"] is not None
    ]

    aggregate_profit = 0.0
    aggregate_loss = 0.0

    for x in results:
        pf = x["profit_factor"]

        if pf is not None:
            # PF is not additive, so this is intentionally
            # calculated from fold PnL components below only
            # in the detailed result.
            pass

    output = {
        "phase": "5E",
        "strategy": "BEARISH + BULLISH SWEEP",
        "entry_model": "B - OB NEAR-EDGE / FIRST-TOUCH",
        "validation": "EXPANDING WALK-FORWARD",
        "dataset": {
            "d1_candles": len(d1),
            "h4_candles": len(h4),
            "start": h4[0]["timestamp"],
            "end": h4[-1]["timestamp"],
        },
        "parameters": {
            "starting_equity": STARTING_EQUITY,
            "risk_pct": RISK_PCT,
            "min_rr": MIN_RR,
            "fee_rate": FEE_RATE,
            "slippage_bps": SLIPPAGE_BPS,
            "initial_train_months": INITIAL_TRAIN_MONTHS,
            "test_months": TEST_MONTHS,
        },
        "walk_forward_summary": {
            "folds": len(results),
            "resolved": resolved,
            "wins": wins,
            "losses": losses,
            "partials": partials,
            "no_entries": no_entries,
            "win_rate_pct": (
                wins / resolved * 100.0
                if resolved
                else 0.0
            ),
            "total_pnl": total_pnl,
            "return_pct": total_pnl / STARTING_EQUITY * 100.0,
            "positive_expectancy_folds": positive_folds,
            "profitable_folds": profitable_folds,
            "positive_expectancy_fold_pct": (
                positive_folds / len(results) * 100.0
                if results
                else 0.0
            ),
            "profitable_fold_pct": (
                profitable_folds / len(results) * 100.0
                if results
                else 0.0
            ),
            "fold_profit_factor_values": fold_pf_values,
        },
        "folds": results,
    }

    with open("phase5e_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
