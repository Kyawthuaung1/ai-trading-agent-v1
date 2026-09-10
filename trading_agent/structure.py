def pivots(c, left=2, right=2):
    highs, lows = [], []

    for i in range(left, len(c) - right):
        h = c[i]["high"]
        l = c[i]["low"]

        left_highs = [x["high"] for x in c[i-left:i]]
        right_highs = [x["high"] for x in c[i+1:i+right+1]]

        left_lows = [x["low"] for x in c[i-left:i]]
        right_lows = [x["low"] for x in c[i+1:i+right+1]]

        if h > max(left_highs) and h >= max(right_highs):
            highs.append((i, h))

        if l < min(left_lows) and l <= min(right_lows):
            lows.append((i, l))

    return highs, lows


def tag(x):
    if len(x) < 2:
        return "insufficient"

    if x[-1][1] > x[-2][1]:
        return "HH"

    if x[-1][1] < x[-2][1]:
        return "LH"

    return "equal"


def low_tag(x):
    if len(x) < 2:
        return "insufficient"

    if x[-1][1] > x[-2][1]:
        return "HL"

    if x[-1][1] < x[-2][1]:
        return "LL"

    return "equal"


def market_structure(c):
    highs, lows = pivots(c)

    return {
        "highs": highs,
        "lows": lows,
        "high_structure": tag(highs),
        "low_structure": low_tag(lows),
    }


def structure_bias(s):
    h = s["high_structure"]
    l = s["low_structure"]

    if h == "HH" and l == "HL":
        return "bullish"

    if h == "LH" and l == "LL":
        return "bearish"

    if h == "HH" and l == "HH":
        return "bullish"

    if h == "LH" and l == "LH":
        return "bearish"

    return "neutral"


def break_events(c):
    """
    Confirmed BOS / CHoCH using completed swing levels.

    A bullish break occurs when the latest close breaks
    the most recent confirmed swing high.

    A bearish break occurs when the latest close breaks
    the most recent confirmed swing low.
    """

    if len(c) < 10:
        return {
            "event": "NONE",
            "bias": "neutral",
            "BOS": False,
            "CHoCH": False,
            "level": None,
            "index": None,
        }

    highs, lows = pivots(c)

    if not highs or not lows:
        return {
            "event": "NONE",
            "bias": "neutral",
            "BOS": False,
            "CHoCH": False,
            "level": None,
            "index": None,
        }

    current = c[-1]
    close = current["close"]

    # Exclude swings created by the current candle.
    confirmed_highs = [x for x in highs if x[0] < len(c) - 1]
    confirmed_lows = [x for x in lows if x[0] < len(c) - 1]

    if not confirmed_highs or not confirmed_lows:
        return {
            "event": "NONE",
            "bias": "neutral",
            "BOS": False,
            "CHoCH": False,
            "level": None,
            "index": None,
        }

    high_level = confirmed_highs[-1][1]
    low_level = confirmed_lows[-1][1]

    # Determine prior directional structure before current candle.
    previous = market_structure(c[:-1])
    previous_bias = structure_bias(previous)

    if close > high_level:
        event = "CHoCH" if previous_bias == "bearish" else "BOS"

        return {
            "event": event,
            "bias": "bullish",
            "BOS": event == "BOS",
            "CHoCH": event == "CHoCH",
            "level": high_level,
            "index": len(c) - 1,
        }

    if close < low_level:
        event = "CHoCH" if previous_bias == "bullish" else "BOS"

        return {
            "event": event,
            "bias": "bearish",
            "BOS": event == "BOS",
            "CHoCH": event == "CHoCH",
            "level": low_level,
            "index": len(c) - 1,
        }

    return {
        "event": "NONE",
        "bias": "neutral",
        "BOS": False,
        "CHoCH": False,
        "level": None,
        "index": None,
    }


def historical_break_events(c, lookback=100):
    """
    Scan historical candles for confirmed BOS / CHoCH events.
    Returns newest events first.
    """

    if len(c) < 15:
        return []

    start = max(10, len(c) - lookback)
    events = []

    for i in range(start, len(c)):
        event = break_events(c[:i+1])

        if event["event"] != "NONE":
            event = dict(event)
            event["index"] = i
            events.append(event)

    return list(reversed(events))


def bos(c):
    return break_events(c)
