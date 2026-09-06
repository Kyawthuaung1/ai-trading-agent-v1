import csv
from datetime import datetime

def load_csv(path):
    out=[]
    with open(path,encoding='utf-8',newline='') as f:
        for r in csv.DictReader(f):
            t=r['timestamp'].strip()
            try: t=datetime.fromtimestamp(float(t))
            except ValueError: t=datetime.fromisoformat(t.replace('Z','+00:00'))
            out.append({'timestamp':t,'open':float(r['open']),'high':float(r['high']),'low':float(r['low']),'close':float(r['close']),'volume':float(r['volume'])})
    if len(out)<30: raise ValueError('Need at least 30 candles')
    return out
