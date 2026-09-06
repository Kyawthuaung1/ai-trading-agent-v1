def pivots(c,left=2,right=2):
    hs=[]; ls=[]
    for i in range(left,len(c)-right):
        h=c[i]['high']; l=c[i]['low']
        if h>max(x['high'] for x in c[i-left:i]) and h>=max(x['high'] for x in c[i+1:i+right+1]): hs.append((i,h))
        if l<min(x['low'] for x in c[i-left:i]) and l<=min(x['low'] for x in c[i+1:i+right+1]): ls.append((i,l))
    return hs,ls

def tag(x):
    if len(x)<2:return 'insufficient'
    return 'HH' if x[-1][1]>x[-2][1] else 'LH' if x[-1][1]<x[-2][1] else 'equal'

def market_structure(c):
    h,l=pivots(c); return {'highs':h,'lows':l,'high_structure':tag(h),'low_structure':tag(l)}

def bos(c):
    h,l=pivots(c); close=c[-1]['close']
    bull=bool(h) and close>h[-1][1]; bear=bool(l) and close<l[-1][1]
    return {'BOS':bull or bear,'CHoCH':False,'bias':'bullish' if bull else 'bearish' if bear else 'neutral'}
