from bisect import bisect_left

from .structure import structure_bias
from .smc import (
    recent_sweep,
    recent_displacement,
    order_block,
)


def _tag(x):
    if len(x) < 2:
        return "insufficient"
    if x[-1][1] > x[-2][1]:
        return "HH"
    if x[-1][1] < x[-2][1]:
        return "LH"
    return "equal"


def _low_tag(x):
    if len(x) < 2:
        return "insufficient"
    if x[-1][1] > x[-2][1]:
        return "HL"
    if x[-1][1] < x[-2][1]:
        return "LL"
    return "equal"


def _bias(highs, lows):
    return structure_bias({
        "high_structure": _tag(highs),
        "low_structure": _low_tag(lows),
    })


def _event(candles, highs, lows, previous_highs, previous_lows, index):
    if len(candles) < 10 or not highs or not lows:
        return {
            "event": "NONE",
            "bias": "neutral",
            "BOS": False,
            "CHoCH": False,
            "level": None,
            "index": None,
        }

    close = candles[-1]["close"]

    previous_bias = _bias(previous_highs, previous_lows)

    high_level = highs[-1][1]
    low_level = lows[-1][1]

    if close > high_level:
        event = "CHoCH" if previous_bias == "bearish" else "BOS"
        return {
            "event": event,
            "bias": "bullish",
            "BOS": event == "BOS",
            "CHoCH": event == "CHoCH",
            "level": high_level,
            "index": index,
        }

    if close < low_level:
        event = "CHoCH" if previous_bias == "bullish" else "BOS"
        return {
            "event": event,
            "bias": "bearish",
            "BOS": event == "BOS",
            "CHoCH": event == "CHoCH",
            "level": low_level,
            "index": index,
        }

    return {
        "event": "NONE",
        "bias": "neutral",
        "BOS": False,
        "CHoCH": False,
        "level": None,
        "index": None,
    }


def historical_mtf_events_fast(d1, h4):
    results = []

    d1_times = [
        x.get("timestamp") or ""
        for x in d1
    ]

    d1_cache = {}

    def get_d1_context(h4_time):
        if h4_time:
            k = bisect_left(d1_times, h4_time)
            d1_slice = d1[:k]
            cache_key = k
        else:
            d1_slice = d1
            cache_key = len(d1)

        if len(d1_slice) < 30:
            return None

        if cache_key not in d1_cache:
            from .mtf import timeframe_context
            d1_cache[cache_key] = timeframe_context(d1_slice)

        return d1_cache[cache_key]

    highs = []
    lows = []

    for i in range(len(h4)):
        center = i - 2

        previous_highs = highs[:]
        previous_lows = lows[:]

        if center >= 2:
            h = h4[center]["high"]
            l = h4[center]["low"]

            left_highs = [
                h4[center - 2]["high"],
                h4[center - 1]["high"],
            ]
            right_highs = [
                h4[center + 1]["high"],
                h4[center + 2]["high"],
            ]

            left_lows = [
                h4[center - 2]["low"],
                h4[center - 1]["low"],
            ]
            right_lows = [
                h4[center + 1]["low"],
                h4[center + 2]["low"],
            ]

            if h > max(left_highs) and h >= max(right_highs):
                highs.append((center, h))

            if l < min(left_lows) and l <= min(right_lows):
                lows.append((center, l))

        if i < 40:
            continue

        if not highs or not lows:
            continue

        h4_bias = _bias(highs, lows)

        event = _event(
            h4[:i + 1],
            highs,
            lows,
            previous_highs,
            previous_lows,
            i,
        )

        h4ctx = {
            "bias": h4_bias,
            "structure": {
                "highs": highs[:],
                "lows": lows[:],
                "high_structure": _tag(highs),
                "low_structure": _low_tag(lows),
            },
            "event": event,
            "last_close": h4[i]["close"],
        }

        h4_time = h4[i].get("timestamp")
        d1ctx = get_d1_context(h4_time)

        if d1ctx is None:
            continue

        direction = event["bias"]

        if direction not in ("bullish", "bearish"):
            continue

        sweep = recent_sweep(h4[:i + 1])
        disp = recent_displacement(h4[:i + 1])

        ob = None

        if disp and disp["direction"] == direction:
            ob = order_block(
                h4[:i + 1],
                direction,
                anchor_index=disp["index"],
            )

        aligned = (
            d1ctx["bias"] == direction
            or d1ctx["bias"] == "neutral"
        )

        if not aligned or not ob:
            continue

        results.append({
            "index": i,
            "direction": direction,
            "d1_bias": d1ctx["bias"],
            "h4_bias": h4ctx["bias"],
            "event": event,
            "sweep": sweep,
            "displacement": disp,
            "order_block": ob,
            "last_close": h4[i]["close"],
        })

    return results
