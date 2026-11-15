import numpy as np
import pandas as pd
p=pd.Series(10+np.arange(120)*.015+.8*np.sin(np.arange(120)/3))
returns=p.pct_change(fill_method=None).fillna(0)
trend=(p.rolling(3).mean()>p.rolling(10).mean())
vol=returns.rolling(10).std(ddof=0)
def evaluate(use_filter, allocation):
    signal=trend & ((vol<.018) if use_filter else True)
    held=(signal.astype(float)*allocation).shift(1,fill_value=0)
    turnover=held.diff().abs().fillna(held.iloc[0])
    net=held*returns-turnover*.001
    return float((1+net).prod()-1), float(turnover.sum())
rows=[]
for filtered, allocation in [(False,1.),(True,1.),(False,.5),(True,.5)]:
    rows.append((filtered,allocation,*evaluate(filtered,allocation)))
print(pd.DataFrame(rows,columns=["波动过滤","仓位","收益","换手"]).round(4))
assert len(rows)==4
assert rows[2][3] <= rows[0][3]

