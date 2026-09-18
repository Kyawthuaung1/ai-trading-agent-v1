"""Phase 5M: canonical exit-path forensics.

This script intentionally reuses build_trade/simulate_trade from backtest_mtf.py
for the authoritative outcome. The additional path classifier mirrors the
canonical ordering: stop first, then TP1/TP2/TP3, with TP1 moving the remaining
stop to actual entry breakeven. It is diagnostic only and does not optimize
parameters or create trading execution logic.
"""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from trading_agent.backtest_mtf import (
    build_trade,
    deduplicate_candidates,
    simulate_trade,
)
from trading_agent.mtf_fast import historical_mtf_events_fast

DATA_DIR = Path("examples")
D1_FILE = DATA_DIR / "BTCUSDT_1d_3y.csv"
H4_FILE = DATA_DIR / "BTCUSDT_4h_3y.csv"
MAX_BARS = 30
RISK_PCT = 0.005
FEE_RATE = 0.0004
SLIPPAGE_BPS = 2.0
MIN_RR = 2.0


def load_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return [
            {
                "timestamp": row["timestamp"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
            for row in csv.DictReader(f)
        ]


def first_entry_index(candles, trade):
    for index in range(trade["signal_index"] + 1, min(len(candles), trade["signal_index"] + 1 + MAX_BARS)):
        candle = candles[index]
        if candle["low"] <= trade["entry"] <= candle["high"]:
            return index
    return None


def price_excursions(candles, trade, entry_index, end_index):
    risk = trade["risk"]
    entry = trade["entry"]
    favorable = []
    adverse = []
    for candle in candles[entry_index : end_index + 1]:
        if trade["direction"] == "bullish":
            favorable.append((candle["high"] - entry) / risk)
            adverse.append((entry - candle["low"]) / risk)
        else:
            favorable.append((entry - candle["low"]) / risk)
            adverse.append((candle["high"] - entry) / risk)
    return max(favorable, default=0.0), max(adverse, default=0.0)


def classify_canonical_path(candles, trade):
    """Mirror canonical event ordering without calculating PnL a second time."""
    start = trade["signal_index"] + 1
    end = min(len(candles), start + MAX_BARS)
    entry_index = first_entry_index(candles, trade)
    if entry_index is None:
        return {"path": "NO_ENTRY", "entry_index": None, "exit_index": end - 1, "same_candle_stop_target": False, "targets_hit": []}

    direction = trade["direction"]
    entered = False
    targets = []
    current_stop = trade["stop"]
    actual_entry = trade["entry"]
    same_candle = False
    for index in range(start, end):
        candle = candles[index]
        if not entered:
            if candle["low"] <= trade["entry"] <= candle["high"]:
                entered = True
            else:
                continue
        hit_stop = candle["low"] <= current_stop if direction == "bullish" else candle["high"] >= current_stop
        hit_tp1 = candle["high"] >= trade["tp1"] if direction == "bullish" else candle["low"] <= trade["tp1"]
        hit_tp2 = candle["high"] >= trade["tp2"] if direction == "bullish" else candle["low"] <= trade["tp2"]
        hit_tp3 = candle["high"] >= trade["tp3"] if direction == "bullish" else candle["low"] <= trade["tp3"]
        if hit_stop:
            same_candle = hit_tp1 or hit_tp2 or hit_tp3
            return {"path": "SL_FIRST" if not targets else "BREAKEVEN_OR_SL_AFTER_TARGET", "entry_index": entry_index, "exit_index": index, "same_candle_stop_target": same_candle, "targets_hit": targets}
        if "TP1" not in targets and hit_tp1:
            targets.append("TP1")
            current_stop = actual_entry
        if "TP2" not in targets and hit_tp2:
            targets.append("TP2")
        if "TP3" not in targets and hit_tp3:
            targets.append("TP3")
        if "TP3" in targets:
            return {"path": "TP3_COMPLETE", "entry_index": entry_index, "exit_index": index, "same_candle_stop_target": same_candle, "targets_hit": targets}
    return {"path": "TIMEOUT_AFTER_ENTRY" if not targets else "PARTIAL_TIMEOUT", "entry_index": entry_index, "exit_index": end - 1, "same_candle_stop_target": same_candle, "targets_hit": targets}


def main():
    d1 = load_csv(D1_FILE)
    h4 = load_csv(H4_FILE)
    candidates = deduplicate_candidates(historical_mtf_events_fast(d1, h4), min_gap=6)
    equity = 10000.0
    records = []
    for candidate in candidates:
        trade = build_trade(candidate, h4, min_rr=MIN_RR)
        if not trade:
            continue
        outcome = simulate_trade(h4, trade, starting_equity=equity, risk_pct=RISK_PCT, fee_rate=FEE_RATE, slippage_bps=SLIPPAGE_BPS, max_bars=MAX_BARS)
        path = classify_canonical_path(h4, trade)
        if path["entry_index"] is not None:
            mfe, mae = price_excursions(h4, trade, path["entry_index"], path["exit_index"])
        else:
            mae, mfe = 0.0, 0.0
        record = {
            "signal_index": trade["signal_index"],
            "timestamp": h4[trade["signal_index"]]["timestamp"],
            "direction": trade["direction"],
            "entry_delay_bars": None if path["entry_index"] is None else path["entry_index"] - trade["signal_index"],
            "canonical_result": outcome["result"],
            "canonical_r_multiple": outcome["r_multiple"],
            "canonical_targets_hit": outcome["targets_hit"],
            "path": path["path"],
            "path_targets_hit": path["targets_hit"],
            "same_candle_stop_target": path["same_candle_stop_target"],
            "mae_r": mae,
            "mfe_r": mfe,
            "exit_index": outcome["exit_index"],
        }
        records.append(record)
        equity += outcome.get("pnl", 0.0)

    path_counts = Counter(record["path"] for record in records)
    result_counts = Counter(record["canonical_result"] for record in records)
    delay_buckets = Counter(
        "NO_ENTRY" if r["entry_delay_bars"] is None else "0-1" if r["entry_delay_bars"] <= 1 else "2-5" if r["entry_delay_bars"] <= 5 else "6-15" if r["entry_delay_bars"] <= 15 else "16+"
        for r in records
    )
    summary = {
        "phase": "5M",
        "mission": "CANONICAL EXIT-PATH FORENSICS",
        "methodology": {
            "canonical_simulator": "trading_agent.backtest_mtf.simulate_trade",
            "same_candle_rule": "SL is processed before TP targets",
            "tp1_rule": "TP1 moves remaining stop to actual entry breakeven",
            "entry_model": "OB midpoint",
            "lookahead": "none; only candles after signal index are scanned",
        },
        "dataset": {"d1_candles": len(d1), "h4_candles": len(h4), "start": h4[0]["timestamp"], "end": h4[-1]["timestamp"]},
        "parameters": {"max_bars": MAX_BARS, "risk_pct": RISK_PCT, "fee_rate": FEE_RATE, "slippage_bps": SLIPPAGE_BPS, "min_rr": MIN_RR},
        "candidate_count": len(records),
        "canonical_result_counts": dict(result_counts),
        "path_counts": dict(path_counts),
        "entry_delay_buckets": dict(delay_buckets),
        "same_candle_stop_target_count": sum(r["same_candle_stop_target"] for r in records),
        "losses_reaching_1r_mfe": sum(r["canonical_result"] in {"LOSS", "PARTIAL"} and r["mfe_r"] >= 1.0 for r in records),
        "losses_reaching_2r_mfe": sum(r["canonical_result"] in {"LOSS", "PARTIAL"} and r["mfe_r"] >= 2.0 for r in records),
        "record_count": len(records),
        "records": records,
        "limitations": [
            "Remote repository state contains Phase 5H but no Phase 5J/5K/5L/5M artifacts; this is a fresh canonical 5M-equivalent analysis.",
            "Only the canonical midpoint entry model is analyzed here; model comparison requires the absent prior phase artifacts or an explicitly scoped new experiment.",
            "MAE/MFE are candle-range excursions through canonical exit_index and are diagnostic, not alternate PnL calculations.",
        ],
    }
    Path("phase5m_results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in {"records"}}, indent=2))


if __name__ == "__main__":
    main()
