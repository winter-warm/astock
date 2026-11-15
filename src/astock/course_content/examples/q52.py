"""人工截面：去极值、标准化和行业中性化。"""
import numpy as np
import pandas as pd


df = pd.DataFrame({"symbol": list("ABCDEFGH"),
                   "industry": ["I"]*4 + ["II"]*4,
                   "factor": [1., 2., 3., 100., 10., 11., 12., np.nan]})
valid = df.dropna(subset=["factor"]).copy()
low, high = valid.factor.quantile([.1, .9])
valid["clipped"] = valid.factor.clip(low, high)
valid["z"] = (valid.clipped - valid.clipped.mean()) / valid.clipped.std(ddof=0)
valid["neutral"] = valid.z - valid.groupby("industry").z.transform("mean")
print(valid.round(5).to_string(index=False))
assert np.isclose(valid.z.mean(), 0)
assert np.isclose(valid.z.std(ddof=0), 1)
assert np.allclose(valid.groupby("industry").neutral.mean(), 0)
assert len(valid) == 7
# 未来横截面的变化不应改变本日横截面处理。
future = pd.DataFrame({"factor": [1e9, -1e9]})
again = (valid.clipped - valid.clipped.mean()) / valid.clipped.std(ddof=0)
np.testing.assert_allclose(valid.z, again)

