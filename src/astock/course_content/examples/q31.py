import numpy as np
import pandas as pd
close = pd.Series([10., 10.2, 9.8, 10., 8., 8.5, 9.5, 10., 7., 6., 5.])
mean = close.rolling(3).mean()
std = close.rolling(3).std(ddof=0)
lower = mean - 1.0 * std
state = 0
entry = None
target, reasons = [], []
for i, p in close.items():
    reason = "等待"
    if pd.notna(mean[i]):
        if state and (p >= mean[i] or p < entry * .90):
            state, reason = 0, "回归均值或收盘止损信号"
        elif not state and p < lower[i]:
            state, entry, reason = 1, p, "低于下轨"
    target.append(state)
    reasons.append(reason)
print(pd.DataFrame(dict(close=close, mean=mean, lower=lower, target=target, reason=reasons)).round(3))
assert target[4] == 1
assert target[6] == 0
assert np.isclose(mean[4], (9.8+10+8)/3)

