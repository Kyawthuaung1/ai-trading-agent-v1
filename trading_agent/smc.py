def _near(a, b, tolerance):
    return abs(a - b) <= tolerance


def equal_highs(c, lookback=50, tolerance_ratio=0.001):
    if len(c) < 5:
        return []

    start = max(0, len(c) - lookback)
    result = []

    for i in range(start + 2, len(c)):
        level = c[i]["high"]
        previous = max(x["high"] for x in c[start:i])

        tolerance = level * tolerance_ratio

        if _near(level, previous, tolerance):
            result.append({
                "type": "EQH",
                "level": level,
                "index": i,
            })

    return result


def equal_lows(c, lookback=50, tolerance_ratio=0.001):
    if len(c) < 5:
        return []

    start = max(0, len(c) - lookback)
    result = []

    for i in range(start + 2, len(c)):
        level = c[i]["low"]
        previous = min(x["low"] for x in c[start:i])

        tolerance = level * tolerance_ratio

        if _near(level, previous, tolerance):
            result.append({
                "type": "EQL",
                "level": level,
                "index": i,
            })

    return result


def liquidity_pools(c, lookback=50):
    eqh = equal_highs(c, lookback)
    eql = equal_lows(c, lookback)

    return {
        "buy_side": eqh[-5:],
        "sell_side": eql[-5:],
    }


def liquidity_sweep(c, lookback=20):
    if len(c) < lookback + 2:
        return {"direction": "none", "level": None, "index": None}

    start = max(0, len(c) - lookback - 1)
    prior = c[start:-1]
    last = c[-1]

    high = max(x["high"] for x in prior)
    low = min(x["low"] for x in prior)

    if last["low"] < low and last["close"] > low:
        return {
            "direction": "bullish",
            "level": low,
            "index": len(c) - 1,
        }

    if last["high"] > high and last["close"] < high:
        return {
            "direction": "bearish",
            "level": high,
            "index": len(c) - 1,
        }

    return {"direction": "none", "level": None, "index": None}


def recent_sweep(c, lookback=40, window=8):
    start = max(1, len(c) - lookback)

    for i in range(len(c) - 1, start - 1, -1):
        left = max(0, i - window)
        prior = c[left:i]

        if not prior:
            continue

        high = max(x["high"] for x in prior)
        low = min(x["low"] for x in prior)

        candle = c[i]

        if candle["low"] < low and candle["close"] > low:
            return {
                "direction": "bullish",
                "level": low,
                "index": i,
            }

        if candle["high"] > high and candle["close"] < high:
            return {
                "direction": "bearish",
                "level": high,
                "index": i,
            }

    return {"direction": "none", "level": None, "index": None}


def fair_value_gap(c):
    if len(c) < 3:
        return None

    a, _, d = c[-3], c[-2], c[-1]

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


def recent_fvg(c, lookback=30):
    start = max(0, len(c) - lookback - 2)

    for i in range(len(c) - 1, start + 1, -1):
        a, _, d = c[i-2], c[i-1], c[i]

        if d["low"] > a["high"]:
            return {
                "type": "bullish",
                "low": a["high"],
                "high": d["low"],
                "size": d["low"] - a["high"],
                "index": i,
            }

        if d["high"] < a["low"]:
            return {
                "type": "bearish",
                "low": d["high"],
                "high": a["low"],
                "size": a["low"] - d["high"],
                "index": i,
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


def recent_displacement(c, lookback=8, multiplier=1.5, body_ratio=0.60):
    start = max(0, len(c) - lookback)

    for i in range(len(c) - 1, start - 1, -1):
        if i < 11:
            continue

        window = c[:i+1]

        if displacement(
            window,
            multiplier=multiplier,
            body_ratio=body_ratio,
        ):
            candle = window[-1]

            return {
                "index": i,
                "direction": (
                    "bullish"
                    if candle["close"] > candle["open"]
                    else "bearish"
                ),
            }

    return None


def order_block(c, direction, anchor_index=None, search=15):
    if len(c) < 3:
        return None

    if anchor_index is None:
        anchor_index = len(c) - 1

    start = max(0, anchor_index - search)

    for i in range(anchor_index - 1, start - 1, -1):
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
