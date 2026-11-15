"""人工横截面：指标变为可比较的因子分数。"""
import numpy as np
import pandas as pd


panel = pd.DataFrame({
    "symbol": ["教学甲", "教学乙", "教学丙", "教学丁"],
    "old_close": [10., 20., 8., 30.],
    "close": [11., 21., 8., 27.],
    "next_return": [.03, -.01, .02, -.04],
})
panel["momentum"] = panel["close"] / panel["old_close"] - 1
panel["rank"] = panel["momentum"].rank(ascending=False, method="average")
selected = panel.nsmallest(2, "rank").copy()
weights = pd.Series(0., index=panel.symbol)
weights.loc[selected.symbol] = 1 / len(selected)
realized = float(np.dot(weights.loc[panel.symbol], panel.next_return))
print(panel.to_string(index=False))
print("选中：", selected.symbol.tolist())
print("下期等权组合收益（未扣费）：", round(realized, 6))
assert selected.symbol.tolist() == ["教学甲", "教学乙"]
assert np.isclose(realized, .01)
# 特征不依赖未来收益：破坏标签也不能改变选股。
changed = panel.copy()
changed["next_return"] *= -100
assert changed.nsmallest(2, "rank").symbol.tolist() == selected.symbol.tolist()

