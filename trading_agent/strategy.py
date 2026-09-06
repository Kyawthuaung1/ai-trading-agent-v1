from .levels import levels, atr
from .risk import rr
from .mtf import analyze_mtf


def mtf_setup(d1, h4, min_rr=2.0):
    x = analyze_mtf(d1, h4)

    d1bias = x["d1"]["bias"]
    h4event = x["h4"]["event"]
    h4event_bias = x["h4"]["event"]["bias"]

    sweep = x["sweep"]
    disp = x["displacement"]
    ob = x["order_block"]

    if d1bias == "bullish":
        preferred = "bullish"
    elif d1bias == "bearish":
        preferred = "bearish"
    else:
        return {
            "status": "WAIT",
            "reason": "D1 context is neutral",
            "analysis": x,
        }

    if h4event not in ("BOS", "CHoCH"):
        return {
            "status": "WAIT",
            "reason": "Waiting for H4 BOS/CHoCH confirmation",
            "analysis": x,
        }

    if h4event_bias != preferred:
        return {
            "status": "WAIT",
            "reason": "H4 confirmation conflicts with D1 context",
            "analysis": x,
        }

    if sweep["direction"] != preferred:
        return {
            "status": "WAIT",
            "reason": "Required liquidity sweep is not confirmed",
            "analysis": x,
        }

    if not disp or disp["direction"] != preferred:
        return {
            "status": "WAIT",
            "reason": "Required H4 displacement is not confirmed",
            "analysis": x,
        }

    if ob is None:
        return {
            "status": "WAIT",
            "reason": "No valid H4 order block found",
            "analysis": x,
        }

    side = "LONG" if preferred == "bullish" else "SHORT"

    close = h4[-1]["close"]
    a = atr(h4) or close * 0.01

    if side == "LONG":
        entry = (ob["low"] + ob["high"]) / 2
        stop = min(
            ob["low"] - 0.25 * a,
            sweep["level"] - 0.10 * a,
        )

        if entry >= close:
            entry = close

        risk = entry - stop

        if risk <= 0:
            return {
                "status": "WAIT",
                "reason": "Invalid long risk distance",
                "analysis": x,
            }

        tp = entry + min_rr * risk

    else:
        entry = (ob["low"] + ob["high"]) / 2
        stop = max(
            ob["high"] + 0.25 * a,
            sweep["level"] + 0.10 * a,
        )

        if entry <= close:
            entry = close

        risk = stop - entry

        if risk <= 0:
            return {
                "status": "WAIT",
                "reason": "Invalid short risk distance",
                "analysis": x,
            }

        tp = entry - min_rr * risk

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
        return {
            "status": "WAIT",
            "reason": "No confirmed breakout structure",
            "structure": s,
        }

    r = rr(entry, stop, tp, side)

    return {
        "status": "VALID" if r >= min_rr else "WAIT",
        "side": side,
        "entry": entry,
        "stop": stop,
        "tp1": tp,
        "rr": r,
        "structure": s,
    }
