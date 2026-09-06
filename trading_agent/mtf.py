from .structure import market_structure, structure_bias, break_events
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
