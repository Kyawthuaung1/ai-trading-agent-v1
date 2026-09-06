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


def recent_sweep(c, lookback=40, window=8):
    start = max(1, len(c) - lookback)

    for i in range(len(c) - 1, start - 1, -1):
        left = max(0, i - window)
        prior = c[left:i]

        if not prior:
            continue

        hi = max(x["high"] for x in prior)
        lo = min(x["low"] for x in prior)
        candle = c[i]

        if candle["low"] < lo and candle["close"] > lo:
            return {
                "direction": "bullish",
                "level": lo,
                "index": i,
            }

        if candle["high"] > hi and candle["close"] < hi:
            return {
                "direction": "bearish",
                "level": hi,
                "index": i,
            }

    return {"direction": "none", "level": None, "index": None}


def fair_value_gap(c):
    if len(c) < 3:
        return None

    a, b, d = c[-3], c[-2], c[-1]

    if d["low"] > a["high"]:
        return {
            "type": "bullish",
            "low": a["high"],
            "high": d["low"],
            "size": d["low"] - a["high"],
        }

    if d["high"] < a["low"]:
        return {
            "type": "bearish",
            "low": d["high"],
            "high": a["low"],
            "size": a["low"] - d["high"],
        }

    return None


def displacement(c, multiplier=1.5, body_ratio=0.60):
    if len(c) < 12:
        return False

    bodies = [
        abs(x["close"] - x["open"])
        for x in c[-11:-1]
    ]

    avg_body = sum(bodies) / len(bodies)

    last = c[-1]
    body = abs(last["close"] - last["open"])
    rng = last["high"] - last["low"]

    if rng <= 0 or avg_body <= 0:
        return False

    return (
        body / rng >= body_ratio
        and body >= avg_body * multiplier
    )


def order_block(c, direction, search=10):
    if len(c) < 3:
        return None

    start = max(0, len(c) - search - 1)

    for i in range(len(c) - 2, start - 1, -1):
        x = c[i]

        if direction == "bullish" and x["close"] < x["open"]:
            return {
                "type": "bullish",
                "index": i,
                "low": x["low"],
                "high": x["open"],
            }

        if direction == "bearish" and x["close"] > x["open"]:
            return {
                "type": "bearish",
                "index": i,
                "low": x["open"],
                "high": x["high"],
            }

    return None
