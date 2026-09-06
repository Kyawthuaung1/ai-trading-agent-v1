def levels(c,n=50):
    x=c[-n:]; return min(z['low'] for z in x),max(z['high'] for z in x)
def atr(c,n=14):
    if len(c)<=n:return None
    tr=[]
    for i in range(1,len(c)):
        h,l,pc=c[i]['high'],c[i]['low'],c[i-1]['close']; tr.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(tr[-n:])/n
