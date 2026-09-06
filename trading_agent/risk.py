def rr(entry,stop,target,side):
    risk=abs(entry-stop); reward=target-entry if side=='LONG' else entry-target
    return reward/risk if risk else 0
def position_size(equity,risk_pct,entry,stop):
    return equity*risk_pct/abs(entry-stop) if entry!=stop else 0
