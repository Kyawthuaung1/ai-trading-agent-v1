from .structure import (
    market_structure,
    structure_bias,
    break_events,
    historical_break_events,
)

from .smc import (
    recent_sweep,
    recent_fvg,
    recent_displacement,
    order_block,
    liquidity_pools,
)


def timeframe_context(c):
    s = market_structure(c)

    return {
        "bias": structure_bias(s),
        "structure": s,
        "event": break_events(c),
        "last_close": c[-1]["close"],
    }


def analyze_mtf(d1, h4):
    d1ctx = timeframe_context(d1)
    h4ctx = timeframe_context(h4)

    sweep = recent_sweep(h4)
    fvg = recent_fvg(h4)
    disp = recent_displacement(h4)

    direction = h4ctx["event"]["bias"]

    if direction not in ("bullish", "bearish"):
        direction = h4ctx["bias"]

    ob = None

    if disp and direction in ("bullish", "bearish"):
        ob = order_block(
            h4,
            direction,
            anchor_index=disp["index"],
        )

    pools = liquidity_pools(h4)

    return {
        "d1": d1ctx,
        "h4": h4ctx,
        "sweep": sweep,
        "fvg": fvg,
        "displacement": disp,
        "order_block": ob,
        "liquidity_pools": pools,
    }


def historical_mtf_events(d1, h4):
    """
    Historical H4 event scan.

    Each H4 candle is evaluated using only information
    available up to that candle.
    """

    results = []

    for i in range(40, len(h4)):
        current_h4 = h4[:i + 1]

        h4ctx = timeframe_context(current_h4)

        # Find latest completed D1 candle before H4 candle.
        h4_time = current_h4[-1].get("timestamp")

        d1_slice = d1

        if h4_time:
            filtered = [
                x for x in d1
                if x.get("timestamp") and x["timestamp"] < h4_time
            ]

            if filtered:
                d1_slice = filtered

        if len(d1_slice) < 30:
            continue

        d1ctx = timeframe_context(d1_slice)

        event = break_events(current_h4)
        sweep = recent_sweep(current_h4)
        disp = recent_displacement(current_h4)

        direction = event["bias"]

        if direction not in ("bullish", "bearish"):
            continue

        ob = None

        if disp and disp["direction"] == direction:
            ob = order_block(
                current_h4,
                direction,
                anchor_index=disp["index"],
            )

        # Historical setup candidate.
        # We deliberately require the directional structure,
        # but do not require every optional SMC component.
        aligned = (
            d1ctx["bias"] == direction
            or d1ctx["bias"] == "neutral"
        )

        if not aligned:
            continue

        if not ob:
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
            "last_close": current_h4[-1]["close"],
        })

    return results
