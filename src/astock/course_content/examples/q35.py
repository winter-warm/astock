import numpy as np
import pandas as pd
samples = {
    "上涨": np.linspace(10,16,60),
    "下跌": np.linspace(16,10,60),
    "震荡": 10 + .6*np.sin(np.arange(60)*1.1),
    "高波动": 10*np.cumprod(1+np.tile([.08,-.07,.05,-.06],15))
}
rows=[]
for name, values in samples.items():
    p=pd.Series(values)
    target=(p.rolling(3).mean()>p.rolling(10).mean()).astype(float)
    held=target.shift(1,fill_value=0)
    costs=held.diff().abs().fillna(held.iloc[0])*.001
    net=held*p.pct_change(fill_method=None).fillna(0)-costs
    equity=(1+net).cumprod()
    peak=equity.cummax().clip(lower=1)
    rows.append([name, equity.iloc[-1]-1, (1-equity/peak).max(), costs.sum()])
result=pd.DataFrame(rows,columns=["情景","收益","最大回撤","成本比例合计"])
print(result.round(4).to_string(index=False))
assert rows[0][1]>0 and rows[1][1]==0
assert all(0 <= row[2] <= 1 for row in rows)

