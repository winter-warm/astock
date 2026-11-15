import numpy as np
import pandas as pd
prices = pd.DataFrame({"A": [10.,11.,12.,11.,10.,9.],
                       "B": [10.,10.2,10.4,10.6,11.,12.]})
momentum = prices / prices.shift(2) - 1
target = pd.DataFrame(0., index=prices.index, columns=prices.columns)
for i in prices.index:
    scores = momentum.loc[i]
    if scores.notna().all() and scores.max() > 0:
        target.loc[i, scores.idxmax()] = .8
held = target.shift(1, fill_value=0)
ret = prices.pct_change(fill_method=None).fillna(0)
gross = (held * ret).sum(axis=1)
print("动量\n", momentum.round(3))
print("目标权重\n", target)
print("滞后一期的组合收益", gross.round(4).tolist())
assert target.loc[2,"A"] == .8 and target.loc[3,"B"] == .8
assert held.loc[3,"A"] == .8
assert np.isclose(gross[3], .8*(11/12-1))

