import pandas as pd
import numpy as np
bars = pd.DataFrame({"open":[10.,11.,10.], "high":[12.,11.5,10.],
                     "low":[9.,9.5,10.], "close":[11.,10.,10.]})
assert (bars["high"] >= bars[["open","close"]].max(axis=1)).all()
assert (bars["low"] <= bars[["open","close"]].min(axis=1)).all()
bars["body"] = (bars["close"]-bars["open"]).abs()
bars["upper_shadow"] = bars["high"]-bars[["open","close"]].max(axis=1)
bars["lower_shadow"] = bars[["open","close"]].min(axis=1)-bars["low"]
bars["range"] = bars["high"]-bars["low"]
bars["body_ratio"] = bars["body"].div(bars["range"].replace(0,np.nan))
print(bars.to_string(index=False))
np.testing.assert_allclose(bars.loc[0,["body","upper_shadow","lower_shadow"]].to_numpy(dtype=float),[1,1,1])
assert pd.isna(bars.loc[2,"body_ratio"])
# 两条不同的柱内路径拥有完全相同 OHLC。
path_a = [10,12,9,11]
path_b = [10,9,12,11]
def ohlc(path):
    return (path[0],max(path),min(path),path[-1])
assert ohlc(path_a) == ohlc(path_b)
print("OHLC 相同，柱内先后顺序仍不同。")


if "lab" in globals():
    lab = globals()["lab"]
    lab.table(bars, title="K 线几何量（人工数据）")
    lab.lines({"开盘": bars["open"], "收盘": bars["close"],
               "最高": bars["high"], "最低": bars["low"]}, title="价格字段对照")
