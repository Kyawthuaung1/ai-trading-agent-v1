from .levels import levels,atr
from .structure import bos,market_structure
from .risk import rr

def setup(c,min_rr=2):
    lo,hi=levels(c); a=atr(c) or c[-1]['close']*.01; close=c[-1]['close']; e=bos(c); s=market_structure(c)
    if e['bias']=='bullish':
        entry=close; stop=min(lo,entry-1.5*a); side='LONG'; tp=entry+min_rr*(entry-stop)
    elif e['bias']=='bearish':
        entry=close; stop=max(hi,entry+1.5*a); side='SHORT'; tp=entry-min_rr*(stop-entry)
    else:return {'status':'WAIT','reason':'No confirmed breakout structure','structure':s}
    r=rr(entry,stop,tp,side); return {'status':'VALID' if r>=min_rr else 'WAIT','side':side,'entry':entry,'stop':stop,'tp1':tp,'rr':r,'structure':s}
