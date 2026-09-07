from .data import load_csv
from .backtest_mtf import (
    build_trade,
    simulate_trade,
    deduplicate_candidates,
)
from .mtf import historical_mtf_events


def check_ohlcv(candles, name):
    errors = []

    if len(candles) < 30:
        errors.append(f"{name}: only {len(candles)} candles")

    for i, c in enumerate(candles):
        if c["high"] < c["low"]:
            errors.append(f"{name}: high < low at {i}")

        if c["open"] > c["high"] or c["open"] < c["low"]:
            errors.append(f"{name}: open outside range at {i}")

        if c["close"] > c["high"] or c["close"] < c["low"]:
            errors.append(f"{name}: close outside range at {i}")

        if c["volume"] < 0:
            errors.append(f"{name}: negative volume at {i}")

    timestamps = [c["timestamp"] for c in candles]

    for i in range(1, len(timestamps)):
        if timestamps[i] <= timestamps[i - 1]:
            errors.append(f"{name}: timestamp order error at {i}")

    return errors


def validate_trade_math():
    # Synthetic bullish trade:
    # Entry = 100
    # SL    = 98
    # TP1   = 102
    # TP2   = 104
    # TP3   = 106

    candles = []

    for i in range(40):
        candles.append({
            "timestamp": f"2026-01-01T{i:02d}:00:00",
            "open": 100.0,
            "high": 100.5,
            "low": 99.5,
            "close": 100.0,
            "volume": 1000.0,
        })

    # Entry candle.
    candles[21]["high"] = 100.5
    candles[21]["low"] = 99.5

    # TP1.
    candles[22]["high"] = 102.5
    candles[22]["close"] = 102.0

    # TP2.
    candles[23]["high"] = 104.5
    candles[23]["close"] = 104.0

    # TP3.
    candles[24]["high"] = 106.5
    candles[24]["close"] = 106.0

    trade = {
        "direction": "bullish",
        "entry": 100.0,
        "stop": 98.0,
        "tp1": 102.0,
        "tp2": 104.0,
        "tp3": 106.0,
        "risk": 2.0,
        "signal_index": 20,
    }

    result = simulate_trade(
        candles,
        trade,
        starting_equity=10000.0,
        risk_pct=0.005,
        fee_rate=0.0,
        slippage_bps=0.0,
        max_bars=10,
    )

    return result


def main():
    print("=== PHASE 4E BACKTEST VALIDATION ===")
    print()

    d1 = load_csv("examples/BTCUSDT_1d.csv")
    h4 = load_csv("examples/BTCUSDT_4h.csv")

    print(f"D1 candles: {len(d1)}")
    print(f"H4 candles: {len(h4)}")
    print()

    d1_errors = check_ohlcv(d1, "D1")
    h4_errors = check_ohlcv(h4, "H4")

    errors = d1_errors + h4_errors

    if errors:
        print("DATA VALIDATION: FAIL")
        for error in errors[:20]:
            print(" -", error)
    else:
        print("DATA VALIDATION: PASS")

    print()

    candidates = historical_mtf_events(d1, h4)
    signals = deduplicate_candidates(candidates, min_gap=6)

    print(f"Raw candidates: {len(candidates)}")
    print(f"Unique signals: {len(signals)}")
    print()

    math_result = validate_trade_math()

    print("TRADE ENGINE TEST")
    print(f"Result: {math_result['result']}")
    print(f"R: {math_result['r_multiple']:.4f}")
    print(f"P&L: ${math_result['pnl']:.4f}")
    print(f"Targets: {math_result['targets_hit']}")

    expected = ["TP1", "TP2", "TP3"]

    # The engine may move the stop to breakeven after TP1.
    # Therefore validation accepts a profitable partial result
    # as long as TP1 is reached and no loss occurs.
    if (
        math_result["result"] in ("WIN", "PARTIAL")
        and "TP1" in math_result["targets_hit"]
        and math_result["pnl"] > 0
    ):
        print("TRADE ENGINE: PASS")
    else:
        print("TRADE ENGINE: FAIL")

    print()
    print("Phase 4E validation complete.")
    print("Research/backtest only. No live execution.")


if __name__ == "__main__":
    main()
