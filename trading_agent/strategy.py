from .levels import levels, atr
from .risk import rr
from .mtf import analyze_mtf


def mtf_setup(d1, h4, min_rr=2.0):
    x = analyze_mtf(d1, h4)

    d1bias = x["d1"]["bias"]
    h4bias = x["h4"]["bias"]
    event = x["h4"]["event"]
    sweep = x["sweep"]
    disp = x["displacement"]
    fvg = x["fvg"]
    ob = x["order_block"]

    if d1bias == "bullish" and h4bias == "bullish":
        side = "LONG"
    elif d1bias == "bearish" and h4bias == "bearish":
        side = "SHORT"
    else:
        return {
            "status": "WAIT",
            "reason": "D1/H4 bias not aligned",
            "analysis": x,
        }

    if sweep["direction"] != side.lower():
        return {
            "status": "WAIT",
            "reason": "Liquidity sweep direction does not match setup",
            "analysis": x,
        }

    if event["event"] not in ("BOS", "CHoCH"):
        return {
            "status": "WAIT",
            "reason": "Waiting for H4 BOS/CHoCH confirmation",
            "analysis": x,
        }

    if not disp:
        return {
            "status": "WAIT",
            "reason": "Waiting for H4 displacement",
            "analysis": x,
        }

    if ob is None:
        return {
            "status": "WAIT",
            "reason": "No valid H4 order block found",
            "analysis": x,
        }

    close = h4[-1]["close"]
    a = atr(h4) or close * 0.01

    if side == "LONG":
        entry = (ob["low"] + ob["high"]) / 2
        stop = min(
            ob["low"] - 0.25 * a,
            sweep["level"] - 0.10 * a,
        )
        risk = entry - stop
        tp = entry + min_rr * risk

        if entry >= close:
            entry = close
            risk = entry - stop
            tp = entry + min_rr * risk

    else:
        entry = (ob["low"] + ob["high"]) / 2
        stop = max(
            ob["high"] + 0.25 * a,
            sweep["level"] + 0.10 * a,
        )
        risk = stop - entry
        tp = entry - min_rr * risk

        if entry <= close:
            entry = close
            risk = stop - entry
            tp = entry - min_rr * risk

    if risk <= 0:
        return {
            "status": "WAIT",
            "reason": "Invalid risk distance",
            "analysis": x,
        }

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
