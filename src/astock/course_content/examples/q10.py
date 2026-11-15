import pandas as pd
import numpy as np

# 虚拟观察序号，不是交易所日历。
observations = pd.Index([0, 1, 2, 3], name="observation")
a = pd.Series([10, 11, 12, 13], index=observations, name="A")
b = pd.Series([20, 22, 24], index=[0, 2, 3], name="B")
panel = pd.concat([a, b], axis=1).reindex(observations)
raw_returns = panel.pct_change(fill_method=None)
filled_returns = panel.ffill().pct_change(fill_method=None)
print("原表\n", panel)
print("不填充的相邻收益\n", raw_returns)
print("前值填充产生的不同结果\n", filled_returns)
assert pd.isna(raw_returns.loc[1, "B"])
assert pd.isna(raw_returns.loc[2, "B"])
assert filled_returns.loc[1, "B"] == 0
np.testing.assert_allclose(filled_returns.loc[2, "B"], .1)
complete = panel.dropna()
assert complete.index.tolist() == [0, 2, 3]
print("仅共同观察时刻", complete.index.tolist())

