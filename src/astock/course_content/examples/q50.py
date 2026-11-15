"""多证券人工行情；因子只使用各时点已完成的历史。"""
import numpy as np
import pandas as pd


rng = np.random.default_rng(50)
returns = rng.normal(0.0002, .01, size=(90, 4))
prices = pd.DataFrame(100 * np.exp(np.cumsum(returns, axis=0)),
                      columns=["A", "B", "C", "D"])
def features(p):
    r = p.pct_change(fill_method=None)
    return {"momentum": p / p.shift(20) - 1,
            "reversal": -(p / p.shift(5) - 1),
            "low_vol": -r.rolling(20, min_periods=20).std(ddof=1)}
f = features(prices)
print(pd.DataFrame({name: value.iloc[50] for name, value in f.items()}).round(6))
future_changed = prices.copy()
future_changed.iloc[51:] *= np.linspace(1, 5, len(prices)-51)[:, None]
for name, value in features(future_changed).items():
    np.testing.assert_allclose(value.iloc[:51], f[name].iloc[:51], equal_nan=True)
assert f["momentum"].iloc[:20].isna().all().all()
assert f["low_vol"].iloc[20:].notna().all().all()
print("未来修改不影响历史因子：通过")

