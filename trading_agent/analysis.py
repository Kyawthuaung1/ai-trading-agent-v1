from .strategy import setup, mtf_setup
from .structure import bos, market_structure
from .levels import levels, atr


def analyze(c):
    lo, hi = levels(c)
    s = market_structure(c)
    e = bos(c)
    q = setup(c)

    lines = [
        "=== AI TRADING AGENT v1 ===",
        f"Last close: {c[-1]['close']:.8f}",
        f"Structure: highs={s['high_structure']}, lows={s['low_structure']}",
        f"BOS={e['BOS']} | CHoCH={e['CHoCH']} | Bias={e['bias']}",
        f"Support: {lo:.8f}",
        f"Resistance: {hi:.8f}",
        f"ATR14: {(atr(c) or 0):.8f}",
        "",
        "TRADE PLAN",
        f"Status: {q['status']}",
    ]

    if "side" in q:
        lines += [
            f"Side: {q['side']}",
            f"Entry: {q['entry']:.8f}",
            f"SL: {q['stop']:.8f}",
            f"TP1: {q['tp1']:.8f}",
            f"RR: 1:{q['rr']:.2f}",
        ]
    else:
        lines += [f"Reason: {q['reason']}"]

    lines += ["", "Research/backtest only. No live execution."]
    return {"setup": q, "report": "\n".join(lines)}


def analyze_mtf_report(d1, h4, min_rr=2.0):
    q = mtf_setup(d1, h4, min_rr)
    x = q["analysis"]

    ds = x["d1"]["structure"]
    hs = x["h4"]["structure"]
    de = x["d1"]["event"]
    he = x["h4"]["event"]
    sweep = x["sweep"]
    fvg = x["fvg"]

    lines = [
        "=== AI TRADING AGENT v2 | D1 + H4 SMC ===",
        "",
        f"D1 Bias: {x['d1']['bias']}",
        f"D1 Structure: highs={ds['high_structure']}, lows={ds['low_structure']}",
        f"D1 Event: {de['event']}",
        "",
        f"H4 Bias: {x['h4']['bias']}",
        f"H4 Structure: highs={hs['high_structure']}, lows={hs['low_structure']}",
        f"H4 Event: {he['event']}",
        "",
        f"Liquidity Sweep: {sweep['direction']}",
    ]

    if sweep["level"] is not None:
        lines.append(f"Sweep Level: {sweep['level']:.8f}")

    if fvg:
        lines.append(
            f"Latest FVG: {fvg['type']} "
            f"{fvg['low']:.8f} - {fvg['high']:.8f}"
        )
    else:
        lines.append("Latest FVG: none")

    lines += [
        f"Displacement: {'yes' if x['displacement'] else 'no'}",
        "",
        "TRADE PLAN",
        f"Status: {q['status']}",
    ]

    if "side" in q:
        lines += [
            f"Side: {q['side']}",
            f"Entry: {q['entry']:.8f}",
            f"SL: {q['stop']:.8f}",
            f"TP1: {q['tp1']:.8f}",
            f"RR: 1:{q['rr']:.2f}",
        ]
    else:
        lines.append(f"Reason: {q['reason']}")

    lines += ["", "Research/backtest only. No live execution."]
    return {"setup": q, "report": "\n".join(lines)}
