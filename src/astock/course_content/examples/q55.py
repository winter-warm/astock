"""人工价格标签：标记信息、决策、标签结束时间。"""
import numpy as np
import pandas as pd

p = pd.Series([100., 101., 99., 102., 104., 103., 106., 108.])
horizon = 2
frame = pd.DataFrame({"close": p, "feature": p.pct_change(fill_method=None)})
frame["target"] = p.shift(-horizon) / p - 1
frame["decision_index"] = frame.index
frame["label_end"] = frame.index + horizon
usable = frame.dropna(subset=["feature", "target"]).copy()
usable["direction"] = (usable.target > .01).astype(int)
print(usable.round(6).to_string(index=False))
assert np.isclose(usable.loc[1, "target"], 102/101 - 1)
assert usable.label_end.max() < len(p)
assert not frame.tail(horizon).target.notna().any()
cut = 5
training = usable[usable.label_end < cut]
evaluation = usable[usable.decision_index >= cut]
assert (training.label_end < cut).all()
assert training.decision_index.max() < evaluation.decision_index.min()
print("训练行：", training.index.tolist(), "评价行：", evaluation.index.tolist())

