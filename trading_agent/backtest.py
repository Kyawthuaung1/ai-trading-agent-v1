from .strategy import setup

def run_backtest(c,warmup=30):
    r=[]
    for i in range(warmup,len(c)-1):
        q=setup(c[:i+1]);
        if q['status']!='VALID':continue
        n=c[i+1]
        if q['side']=='LONG':
            if n['low']<=q['stop']:r.append(-1)
            elif n['high']>=q['tp1']:r.append(2)
        else:
            if n['high']>=q['stop']:r.append(-1)
            elif n['low']<=q['tp1']:r.append(2)
    w=sum(x>0 for x in r); l=sum(x<0 for x in r); wr=100*w/len(r) if r else 0; ex=sum(r)/len(r) if r else 0
    return {'trades':r,'report':f'=== BACKTEST v1 ===\nTrades: {len(r)}\nWins: {w}\nLosses: {l}\nWin rate: {wr:.2f}%\nR expectancy/trade: {ex:.3f}\n\nNot modeled yet: fees, slippage, funding, spread, intrabar sequencing.'}
