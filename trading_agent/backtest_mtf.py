from .data import load_csv
from .mtf import historical_mtf_events


def _atr(c, period=14):
    if len(c) < period + 1:
        return 0.0

    trs = []

    for i in range(1, len(c)):
        high = c[i]["high"]
        low = c[i]["low"]
        prev_close = c[i - 1]["close"]

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )

        trs.append(tr)

    values = trs[-period:]

    if not values:
        return 0.0

    return sum(values) / len(values)


def build_trade(signal, candles, min_rr=2.0):
    direction = signal["direction"]
    ob = signal["order_block"]

    if not ob:
        return None

    entry = (ob["low"] + ob["high"]) / 2.0
    atr = _atr(candles[:signal["index"] + 1])

    if atr <= 0:
        atr = abs(ob["high"] - ob["low"])

    if atr <= 0:
        return None

    if direction == "bullish":
        stop = min(
            ob["low"] - atr * 0.25,
            ob["low"] - 0.0001,
        )

        risk = entry - stop

        if risk <= 0:
            return None

        target = entry + risk * min_rr

    else:
        stop = max(
            ob["high"] + atr * 0.25,
            ob["high"] + 0.0001,
        )

        risk = stop - entry

        if risk <= 0:
            return None

        target = entry - risk * min_rr

    return {
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk": risk,
        "signal_index": signal["index"],
    }


def simulate_trade(candles, trade, max_bars=30):
    start = trade["signal_index"] + 1
    end = min(len(candles), start + max_bars)

    direction = trade["direction"]
    entry = trade["entry"]
    stop = trade["stop"]
    target = trade["target"]

    entered = False

    for i in range(start, end):
        candle = candles[i]

        high = candle["high"]
        low = candle["low"]

        # Wait for price to actually reach the entry.
        if not entered:
            if low <= entry <= high:
                entered = True
            else:
                continue

        if direction == "bullish":
            hit_stop = low <= stop
            hit_target = high >= target
        else:
            hit_stop = high >= stop
            hit_target = low <= target

        # Conservative assumption:
        # if SL and TP happen in the same candle,
        # count the trade as a loss.
        if hit_stop and hit_target:
            return {
                "result": "LOSS",
                "exit_index": i,
                "reason": "SL_and_TP_same_candle",
            }

        if hit_stop:
            return {
                "result": "LOSS",
                "exit_index": i,
                "reason": "SL",
            }

        if hit_target:
            return {
                "result": "WIN",
                "exit_index": i,
                "reason": "TP",
            }

    if entered:
        return {
            "result": "TIMEOUT",
            "exit_index": end - 1,
            "reason": "max_bars",
        }

    return {
        "result": "NO_ENTRY",
        "exit_index": end - 1,
        "reason": "entry_not_reached",
    }


def run_mtf_backtest(d1, h4, min_rr=2.0):
    candidates = historical_mtf_events(d1, h4)

    signals = []
    wins = 0
    losses = 0
    timeouts = 0
    no_entries = 0

    used_indices = set()

    for signal in candidates:
        index = signal["index"]

        # Avoid counting the same setup repeatedly
        # on consecutive candles.
        if index in used_indices:
            continue

        trade = build_trade(
            signal,
            h4,
            min_rr=min_rr,
        )

        if not trade:
            continue

        result = simulate_trade(
            h4,
            trade,
        )

        signals.append({
            "signal": signal,
            "trade": trade,
            "result": result,
        })

        used_indices.add(index)

        if result["result"] == "WIN":
            wins += 1

        elif result["result"] == "LOSS":
            losses += 1

        elif result["result"] == "TIMEOUT":
            timeouts += 1

        elif result["result"] == "NO_ENTRY":
            no_entries += 1

    total_resolved = wins + losses

    if total_resolved:
        win_rate = wins / total_resolved * 100.0
    else:
        win_rate = 0.0

    lines = [
        "=== MTF SMC BACKTEST ===",
        f"Candidates: {len(candidates)}",
        f"Signals: {len(signals)}",
        f"Wins: {wins}",
        f"Losses: {losses}",
        f"Timeouts: {timeouts}",
        f"No entry: {no_entries}",
        f"Resolved trades: {total_resolved}",
        f"Win rate: {win_rate:.2f}%",
        "",
        "Recent signals:",
    ]

    for item in signals[:10]:
        signal = item["signal"]
        trade = item["trade"]
        result = item["result"]

        lines.append(
            f"index={signal['index']} "
            f"direction={signal['direction']} "
            f"event={signal['event']['event']} "
            f"entry={trade['entry']:.2f} "
            f"SL={trade['stop']:.2f} "
            f"TP={trade['target']:.2f} "
            f"result={result['result']}"
        )

    lines.extend([
        "",
        "Research/backtest only.",
        "Fees, slippage and funding are not included yet.",
    ])

    return {
        "signals": signals,
        "wins": wins,
        "losses": losses,
        "timeouts": timeouts,
        "no_entries": no_entries,
        "win_rate": win_rate,
        "report": "\n".join(lines),
    }
