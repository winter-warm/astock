import math
def size_for_risk(equity, cash, entry, stop, risk_fraction=.01, max_weight=.2, lot=100):
    distance=entry-stop
    if distance<=0 or entry<=0:
        raise ValueError("多头止损必须低于入场价")
    risk_qty=equity*risk_fraction/distance
    cash_qty=cash*.98/entry
    weight_qty=equity*max_weight/entry
    raw=min(risk_qty,cash_qty,weight_qty)
    return max(0,math.floor(raw/lot)*lot)
normal=size_for_risk(100000,100000,10,9)
wide=size_for_risk(100000,100000,10,8)
small=size_for_risk(100000,500,10,9)
print("一元风险距离",normal,"两元",wide,"现金不足",small)
assert normal==1000 and wide==500 and small==0
assert normal*(10-9)==1000

