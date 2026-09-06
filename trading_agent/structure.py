def pivots(c, left=2, right=2):
    hs, ls = [], []
    for i in range(left, len(c) - right):
        h, l = c[i]["high"], c[i]["low"]
        if h > max(x["high"] for x in c[i-left:i]) and h >= max(x["high"] for x in c[i+1:i+right+1]):
            hs.append((i, h))
        if l < min(x["low"] for x in c[i-left:i]) and l <= min(x["low"] for x in c[i+1:i+right+1]):
            ls.append((i, l))
    return hs, ls


def tag(x):
    if len(x) < 2:
        return "insufficient"
    return "HH" if x[-1][1] > x[-2][1] else "LH" if x[-1][1] < x[-2][1] else "equal"


def market_structure(c):
    h, l = pivots(c)
    return {
        "highs": h,
        "lows": l,
        "high_structure": tag(h),
        "low_structure": tag(l),
    }


def structure_bias(s):
    h, l = s["high_structure"], s["low_structure"]
    if h == "HH" and l in ("HH", "HL"):
        return "bullish"
    if l == "LL" and h in ("LH", "LL"):
        return "bearish"
    if h == "LH" and l == "LL":
        return "bearish"
    return "neutral"


def break_events(c):
    h, l = pivots(c)
    close = c[-1]["close"]

    bull_bos = bool(h) and close > h[-1][1]
    bear_bos = bool(l) and close < l[-1][1]

    previous = market_structure(c[:-1]) if len(c) > 30 else market_structure(c)
    prev_bias = structure_bias(previous)

    if bull_bos:
        event = "CHoCH" if prev_bias == "bearish" else "BOS"
        return {"BOS": event == "BOS", "CHoCH": event == "CHoCH",
                "event": event, "bias": "bullish"}
    if bear_bos:
        event = "CHoCH" if prev_bias == "bullish" else "BOS"
        return {"BOS": event == "BOS", "CHoCH": event == "CHoCH",
                "event": event, "bias": "bearish"}

    return {"BOS": False, "CHoCH": False, "event": "NONE", "bias": "neutral"}


def bos(c):
    return break_events(c)
