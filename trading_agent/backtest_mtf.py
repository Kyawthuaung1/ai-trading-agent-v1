from .strategy import mtf_setup


def _latest_completed_d1(d1, timestamp):
    candidates = [
        x for x in d1
        if x["timestamp"] < timestamp
    ]

    if not candidates:
        return None

    return candidates[-1]


def run_mtf_backtest(d1, h4, min_rr=2.0, max_trades=1000):
    trades = []
    wins = 0
    losses = 0

    for i in range(40, len(h4) - 1):
        current_h4 = h4[:i + 1]
        ts = h4[i]["timestamp"]

        d1_current = _latest_completed_d1(d1, ts)

        if d1_current is None:
            continue

        d1_index = d1.index(d1_current)

        if d1_index < 30:
            continue

        current_d1 = d1[:d1_index + 1]

        setup = mtf_setup(
            current_d1,
            current_h4,
            min_rr=min_rr,
        )

        if setup["status"] != "VALID":
            continue

        side = setup["side"]
        entry = setup["entry"]
        stop = setup["stop"]
        tp = setup["tp1"]

        result = "OPEN"

        for future in h4[i + 1:]:
            if side == "LONG":
                hit_sl = future["low"] <= stop
                hit_tp = future["high"] >= tp
            else:
                hit_sl = future["high"] >= stop
                hit_tp = future["low"] <= tp

            if hit_sl and hit_tp:
                result = "LOSS"
                break

            if hit_sl:
                result = "LOSS"
                break

            if hit_tp:
                result = "WIN"
                break

        if result == "WIN":
            wins += 1
        elif result == "LOSS":
            losses += 1

        trades.append({
            "index": i,
            "side": side,
            "entry": entry,
            "stop": stop,
            "tp": tp,
            "result": result,
        })

        if len(trades) >= max_trades:
            break

    total = wins + losses
    win_rate = (wins / total * 100) if total else 0.0

    report = "\n".join([
        "=== MTF SMC BACKTEST ===",
        f"Signals: {len(trades)}",
        f"Wins: {wins}",
        f"Losses: {losses}",
        f"Win rate: {win_rate:.2f}%",
        "",
        "Research/backtest only.",
        "Fees, slippage and funding are not included yet.",
    ])

    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "report": report,
    }
