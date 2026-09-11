import csv
import json
from datetime import datetime
from pathlib import Path

from trading_agent.backtest_mtf import atr, deduplicate_candidates, simulate_trade
from trading_agent.mtf_fast import historical_mtf_events_fast

DATA_DIR = Path("examples")
D1_FILE = DATA_DIR / "BTCUSDT_1d_3y.csv"
H4_FILE = DATA_DIR / "BTCUSDT_4h_3y.csv"

STARTING_EQUITY = 10000.0
RISK_PCT = 0.005
BASE_RR = 2.25
BASE_BUFFER = 0.25

BASE_FEE = 0.0004
BASE_SLIPPAGE = 2.0

STRESS_FEE = 0.0006
STRESS_SLIPPAGE = 4.0

RR_VALUES = [2.0, 2.25, 2.5, 3.0]
BUFFER_VALUES = [0.0, 0.25, 0.5]


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

    days = [
        31,
        29 if year % 4 == 0 else 28,
        31, 30, 31, 30,
        31, 31, 30, 31, 30, 31,
    ]

    day = min(dt.day, days[month - 1])
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


def build_b_trade(signal, candles, rr, buffer_atr):
    ob = signal.get("order_block")

    if not ob:
        return None

    index = signal["index"]

    if index >= len(candles) - 1:
        return None

    direction = signal["direction"]

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
        stop = ob["low"] - a * buffer_atr
        risk = entry - stop

        if risk <= 0:
            return None

        tp1 = entry + risk
        tp2 = entry + risk * rr
        tp3 = entry + risk * 3.0

    else:
        stop = ob["high"] + a * buffer_atr
        risk = stop - entry

        if risk <= 0:
            return None

        tp1 = entry - risk
        tp2 = entry - risk * rr
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


def build_folds(candles):
    start = parse_dt(candles[0]["timestamp"])
    end = parse_dt(candles[-1]["timestamp"])

    train_start = start
    test_start = add_months(train_start, 12)

    folds = []

    while test_start < end:
        test_end = add_months(test_start, 6)

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

        test_start = add_months(test_start, 6)

    return folds


def evaluate_fold(
    candidates,
    candles,
    test_start,
    test_end,
    rr,
    buffer_atr,
    fee_rate,
    slippage_bps,
):
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
        trade = build_b_trade(
            signal,
            candles,
            rr,
            buffer_atr,
        )

        if trade is not None:
            trades.append(trade)

    trades.sort(key=lambda x: x["signal_index"])

    unique = []
    last_index = -999999

    for trade in trades:
        if trade["signal_index"] - last_index < 6:
            continue

        unique.append(trade)
        last_index = trade["signal_index"]

    clipped = [
        c for c in candles
        if parse_dt(c["timestamp"]) < test_end
    ]

    equity = STARTING_EQUITY
    peak = equity
    max_dd = 0.0

    wins = 0
    losses = 0
    partials = 0
    no_entries = 0
    resolved = 0

    total_pnl = 0.0
    profit = 0.0
    loss_abs = 0.0
    r_values = []

    for trade in unique:
        result = simulate_trade(
            clipped,
            trade,
            starting_equity=equity,
            risk_pct=RISK_PCT,
            fee_rate=fee_rate,
            slippage_bps=slippage_bps,
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
        "signals": len(selected),
        "unique_trades": len(unique),
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "partials": partials,
        "no_entries": no_entries,
        "win_rate_pct": (
            wins / resolved * 100
            if resolved
            else 0.0
        ),
        "profit_factor": pf,
        "expectancy_r": expectancy_r,
        "pnl": total_pnl,
        "return_pct": total_pnl / STARTING_EQUITY * 100,
        "max_drawdown": max_dd,
    }


def run_variant(
    name,
    candidates,
    candles,
    folds,
    rr,
    buffer_atr,
    fee_rate,
    slippage_bps,
):
    fold_results = []

    for fold in folds:
        result = evaluate_fold(
            candidates,
            candles,
            fold["test_start"],
            fold["test_end"],
            rr,
            buffer_atr,
            fee_rate,
            slippage_bps,
        )

        result["train_start"] = fold["train_start"].isoformat()
        result["train_end"] = fold["train_end"].isoformat()
        result["test_start"] = fold["test_start"].isoformat()
        result["test_end"] = fold["test_end"].isoformat()

        fold_results.append(result)

    resolved = sum(x["resolved"] for x in fold_results)
    wins = sum(x["wins"] for x in fold_results)
    losses = sum(x["losses"] for x in fold_results)
    partials = sum(x["partials"] for x in fold_results)
    no_entries = sum(x["no_entries"] for x in fold_results)
    pnl = sum(x["pnl"] for x in fold_results)

    positive_folds = sum(
        1 for x in fold_results
        if x["expectancy_r"] > 0
    )

    profitable_folds = sum(
        1 for x in fold_results
        if x["pnl"] > 0
    )

    pf_values = [
        x["profit_factor"]
        for x in fold_results
        if x["profit_factor"] is not None
    ]

    expectancy_values = [
        x["expectancy_r"]
        for x in fold_results
    ]

    return {
        "name": name,
        "parameters": {
            "rr": rr,
            "stop_buffer_atr": buffer_atr,
            "fee_rate": fee_rate,
            "slippage_bps": slippage_bps,
        },
        "summary": {
            "folds": len(fold_results),
            "resolved": resolved,
            "wins": wins,
            "losses": losses,
            "partials": partials,
            "no_entries": no_entries,
            "win_rate_pct": (
                wins / resolved * 100
                if resolved
                else 0.0
            ),
            "total_pnl": pnl,
            "return_pct": pnl / STARTING_EQUITY * 100,
            "positive_expectancy_folds": positive_folds,
            "positive_expectancy_fold_pct": (
                positive_folds / len(fold_results) * 100
                if fold_results
                else 0.0
            ),
            "profitable_folds": profitable_folds,
            "profitable_fold_pct": (
                profitable_folds / len(fold_results) * 100
                if fold_results
                else 0.0
            ),
            "min_fold_expectancy_r": (
                min(expectancy_values)
                if expectancy_values
                else 0.0
            ),
            "avg_fold_expectancy_r": (
                sum(expectancy_values) / len(expectancy_values)
                if expectancy_values
                else 0.0
            ),
            "fold_profit_factor_values": pf_values,
        },
        "folds": fold_results,
    }


def main():
    d1 = load_csv(D1_FILE)
    h4 = load_csv(H4_FILE)

    all_candidates = historical_mtf_events_fast(d1, h4)
    candidates = filter_strategy_candidates(all_candidates)
    folds = build_folds(h4)

    results = []

    # 1. RR sensitivity with baseline stop buffer.
    for rr in RR_VALUES:
        results.append(
            run_variant(
                f"RR_{rr}_BUFFER_{BASE_BUFFER}",
                candidates,
                h4,
                folds,
                rr,
                BASE_BUFFER,
                BASE_FEE,
                BASE_SLIPPAGE,
            )
        )

    # 2. Stop-buffer sensitivity with baseline RR.
    for buffer_atr in BUFFER_VALUES:
        if buffer_atr == BASE_BUFFER:
            continue

        results.append(
            run_variant(
                f"RR_{BASE_RR}_BUFFER_{buffer_atr}",
                candidates,
                h4,
                folds,
                BASE_RR,
                buffer_atr,
                BASE_FEE,
                BASE_SLIPPAGE,
            )
        )

    # 3. Cost stress test.
    results.append(
        run_variant(
            "BASELINE_COST",
            candidates,
            h4,
            folds,
            BASE_RR,
            BASE_BUFFER,
            BASE_FEE,
            BASE_SLIPPAGE,
        )
    )

    results.append(
        run_variant(
            "STRESSED_COST",
            candidates,
            h4,
            folds,
            BASE_RR,
            BASE_BUFFER,
            STRESS_FEE,
            STRESS_SLIPPAGE,
        )
    )

    baseline = next(
        x for x in results
        if x["name"] == "BASELINE_COST"
    )

    output = {
        "phase": "5F",
        "strategy": "BEARISH + BULLISH SWEEP",
        "entry_model": "B - OB NEAR-EDGE / FIRST-TOUCH",
        "validation": "ROBUSTNESS / SENSITIVITY LAB",
        "dataset": {
            "d1_candles": len(d1),
            "h4_candles": len(h4),
            "start": h4[0]["timestamp"],
            "end": h4[-1]["timestamp"],
        },
        "base_parameters": {
            "starting_equity": STARTING_EQUITY,
            "risk_pct": RISK_PCT,
            "rr": BASE_RR,
            "stop_buffer_atr": BASE_BUFFER,
            "fee_rate": BASE_FEE,
            "slippage_bps": BASE_SLIPPAGE,
        },
        "candidate_count": len(candidates),
        "fold_count": len(folds),
        "baseline": baseline,
        "variants": results,
        "research_note": (
            "Phase 5F uses a predeclared sensitivity grid. "
            "It is not used to optimize a live strategy. "
            "The purpose is robustness testing across RR, "
            "stop-buffer and transaction-cost assumptions."
        ),
    }

    with open(
        "phase5f_results.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(output, f, indent=2)

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
