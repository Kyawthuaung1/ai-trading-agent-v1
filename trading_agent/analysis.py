from .strategy import setup
from .structure import bos,market_structure
from .levels import levels,atr

def analyze(c):
    lo,hi=levels(c); s=market_structure(c); e=bos(c); q=setup(c)
    lines=['=== AI TRADING AGENT v1 ===',f"Last close: {c[-1]['close']:.8f}",f"Structure: highs={s['high_structure']}, lows={s['low_structure']}",f"BOS={e['BOS']} | CHoCH={e['CHoCH']} | Bias={e['bias']}",f'Support: {lo:.8f}',f'Resistance: {hi:.8f}',f"ATR14: {(atr(c) or 0):.8f}",'','TRADE PLAN',f"Status: {q['status']}"]
    if 'side' in q: lines += [f"Side: {q['side']}",f"Entry: {q['entry']:.8f}",f"SL: {q['stop']:.8f}",f"TP1: {q['tp1']:.8f}",f"RR: 1:{q['rr']:.2f}"]
    else: lines += [f"Reason: {q['reason']}"]
    lines += ['','Research/backtest only. No live execution.']
    return {'setup':q,'report':'\n'.join(lines)}
