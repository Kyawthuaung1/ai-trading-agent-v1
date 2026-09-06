def liquidity_sweep(c, lookback=20):
    if len(c) < lookback + 2:
        return {"direction": "none", "level": None, "index": None}

    start = max(0, len(c) - lookback - 1)
    prior = c[start:-1]
    last = c[-1]

    hi = max(x["high"] for x in prior)
    lo = min(x["low"] for x in prior)

    if last["low"] < lo and last["close"] > lo:
        return {"direction": "bullish", "level": lo, "index": len(c) - 1}

    if last["high"] > hi and last["close"] < hi:
        return {"direction": "bearish", "level": hi, "index": len(c) - 1}

    return {"direction": "none", "level": None, "index": None}


def recent_sweep(c, lookback=30, window=6):
    start = max(1, len(c) - lookback)
    end = len(c)

    for i in range(end - 1, start - 1, -1):
        left = max(0, i - window)
        prior = c[left:i]
        if not prior:
            continue

        hi = max(x["high"] for x in prior)
        lo = min(x["low"] for x in prior)
        candle = c[i]

        if candle["low"] < lo and candle["close"] > lo:
            return {"direction": "bullish", "level": lo, "index": i}

        if candle["high"] > hi and candle["close"] < hi:
            return {"direction": "bearish", "level": hi, "index": i}

    return {"direction": "none", "level": None, "index": None}


def fair_value_gap(c):
    if len(c) < 3:
        return None

    a, _, d = c[-3], c[-2], c[-1]

    if d["low"] > a["high"]:
        return {"type": "bullish", "low": a["high"], "high": d["low"]}

    if d["high"] < a["low"]:
        return {"type": "bearish", "low": d["high"], "high": a["low"]}

    return None


def displacement(c, multiplier=1.5):
    if len(c) < 10:
        return False

    bodies = [abs(x["close"] - x["open"]) for x in c[-10:-1]]
    avg = sum(bodies) / len(bodies)

    last = c[-1]
    body = abs(last["close"] - last["open"])
    rng = last["high"] - last["low"]

    if rng <= 0 or avg <= 0:
        return False

    return body / rng >= 0.60 and body >= avg * multiplier
