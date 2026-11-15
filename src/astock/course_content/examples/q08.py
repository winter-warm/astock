import pandas as pd
import numpy as np

frame = pd.DataFrame({
    "symbol": ["A", "B", "C"], "close": [10.0, 20.0, 8.0],
    "volume": [1000, 500, 0],
}, index=["2026-01-05-A", "2026-01-05-B", "2026-01-05-C"])
active = frame.loc[frame["volume"] > 0, ["symbol", "close"]].copy()
active["amount_for_100"] = active["close"] * 100
print(active.to_string())
assert active["symbol"].tolist() == ["A", "B"]
assert active["amount_for_100"].tolist() == [1000.0, 2000.0]
a = pd.Series([10.0, 20.0], index=["A", "B"])
b = pd.Series([2.0, 1.0], index=["B", "A"])
aligned = a + b
positional = a.to_numpy() + b.to_numpy()
print("标签对齐", aligned.to_dict())
print("位置相加", positional)
assert aligned.to_dict() == {"A": 11.0, "B": 22.0}
np.testing.assert_allclose(positional, [12, 21])

