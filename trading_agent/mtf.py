from .structure import market_structure, structure_bias, break_events
from .smc import (
    recent_sweep,
    fair_value_gap,
    displacement,
    order_block,
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
    fvg = fair_value_gap(h4)
    disp = displacement(h4)

    direction = h4ctx["bias"]

    if h4ctx["event"]["bias"] in ("bullish", "bearish"):
        direction = h4ctx["event"]["bias"]

    ob = order_block(h4, direction) if direction in ("bullish", "bearish") else None

    return {
        "d1": d1ctx,
        "h4": h4ctx,
        "sweep": sweep,
        "fvg": fvg,
        "displacement": disp,
        "order_block": ob,
    }
