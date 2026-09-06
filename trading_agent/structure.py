def pivots(c, left=2, right=2):
    highs, lows = [], []

    for i in range(left, len(c) - right):
        h = c[i]["high"]
        l = c[i]["low"]

        if h > max(x["high"] for x in c[i-left:i]) and \
           h >= max(x["high"] for x in c[i+1:i+right+1]):
            highs.append((i, h))

        if l < min(x["low"] for x in c[i-left:i]) and \
           l <= min(x["low"] for x in c[i+1:i+right+1]):
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
    highs, lows = pivots(c)

    if not highs or not lows:
        return {
            "event": "NONE",
            "bias": "neutral",
            "BOS": False,
            "CHoCH": False,
            "level": None,
        }

    close = c[-1]["close"]

    bull_level = highs[-1][1]
    bear_level = lows[-1][1]

    previous = market_structure(c[:-1]) if len(c) > 30 else market_structure(c)
    previous_bias = structure_bias(previous)

    if close > bull_level:
        event = "CHoCH" if previous_bias == "bearish" else "BOS"
        return {
            "event": event,
            "bias": "bullish",
            "BOS": event == "BOS",
            "CHoCH": event == "CHoCH",
            "level": bull_level,
        }

    if close < bear_level:
        event = "CHoCH" if previous_bias == "bullish" else "BOS"
        return {
            "event": event,
            "bias": "bearish",
            "BOS": event == "BOS",
            "CHoCH": event == "CHoCH",
            "level": bear_level,
        }

    return {
        "event": "NONE",
        "bias": "neutral",
        "BOS": False,
        "CHoCH": False,
        "level": None,
    }


def bos(c):
    return break_events(c)
