"""合成价格；研究信号，不模拟 A 股撮合。"""
import numpy as np
import pandas as pd
close = pd.Series([10., 10., 10., 11., 12., 13., 12., 11., 10., 9.])
fast = close.rolling(2, min_periods=2).mean()
slow = close.rolling(3, min_periods=3).mean()
target = (fast > slow).astype(float)
held = target.shift(1, fill_value=0)
gross = held * close.pct_change(fill_method=None).fillna(0)
turnover = held.diff().abs().fillna(held.iloc[0])
net = gross - turnover * .001
print(pd.DataFrame(dict(close=close, fast=fast, slow=slow, target=target, held=held, net=net)).round(4))
assert target.iloc[3] == 1 and held.iloc[3] == 0
assert held.iloc[4] == 1
assert np.isclose(net.iloc[4], 12/11 - 1 - .001)

