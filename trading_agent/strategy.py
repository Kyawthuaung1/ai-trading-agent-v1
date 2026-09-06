from .levels import levels, atr
from .risk import rr
from .mtf import analyze_mtf


def mtf_setup(d1, h4, min_rr=2.0):
    x = analyze_mtf(d1, h4)

    d1bias = x["d1"]["bias"]
    h4event = x["h4"]["event"]
    h4bias = x["h4"]["bias"]
    sweep = x["sweep"]

    if d1bias == "bullish" and h4bias == "bullish" and sweep["direction"] == "bullish":
        side = "LONG"
    elif d1bias == "bearish" and h4bias == "bearish" and sweep["direction"] == "bearish":
        side = "SHORT"
    else:
        return {
            "status": "WAIT",
            "reason": "D1/H4 bias and liquidity sweep are not aligned",
            "analysis": x,
        }

    if h4event not in ("BOS", "CHoCH"):
        return {
            "status": "WAIT",
            "reason": "Waiting for H4 BOS/CHoCH confirmation after sweep",
            "analysis": x,
        }

    close = h4[-1]["close"]
    a = atr(h4) or close * 0.01
    lo, hi = levels(h4)

    if side == "LONG":
        entry = close
        stop = min(sweep["level"], lo, entry - 1.5 * a)
        tp = entry + min_rr * (entry - stop)
    else:
        entry = close
        stop = max(sweep["level"], hi, entry + 1.5 * a)
        tp = entry - min_rr * (stop - entry)

    actual_rr = rr(entry, stop, tp, side)

    return {
        "status": "VALID" if actual_rr >= min_rr else "WAIT",
        "side": side,
        "entry": entry,
        "stop": stop,
        "tp1": tp,
        "rr": actual_rr,
        "analysis": x,
    }


def setup(c, min_rr=2):
    from .structure import bos, market_structure
    lo, hi = levels(c)
    a = atr(c) or c[-1]["close"] * 0.01
    close = c[-1]["close"]
    e = bos(c)
    s = market_structure(c)

    if e["bias"] == "bullish":
        entry = close
        stop = min(lo, entry - 1.5 * a)
        tp = entry + min_rr * (entry - stop)
        side = "LONG"
    elif e["bias"] == "bearish":
        entry = close
        stop = max(hi, entry + 1.5 * a)
        tp = entry - min_rr * (stop - entry)
        side = "SHORT"
    else:
        return {"status": "WAIT", "reason": "No confirmed breakout structure", "structure": s}

    r = rr(entry, stop, tp, side)
    return {"status": "VALID" if r >= min_rr else "WAIT",
            "side": side, "entry": entry, "stop": stop, "tp1": tp,
            "rr": r, "structure": s}
