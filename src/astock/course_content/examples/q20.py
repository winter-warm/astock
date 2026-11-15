import pandas as pd
import numpy as np
close = pd.Series([10.,11.,12.,11.,13.,12.,10.,9.])
upper = close.rolling(3,min_periods=3).max().shift(1)
lower = close.rolling(3,min_periods=3).min().shift(1)
breakout = (close > upper) & upper.notna()
breakdown = (close < lower) & lower.notna()
result = pd.DataFrame({"close":close,"prior_high":upper,"prior_low":lower,
                       "breakout":breakout,"breakdown":breakdown})
print(result.to_string())
assert breakout.tolist() == [False,False,False,False,True,False,False,False]
assert breakdown.iloc[6]
np.testing.assert_allclose(upper.iloc[4],12)
# 非因果反例：第2位是否是局部高点，要等第3位后才能确认。
local_high_after_next = (close > close.shift(1)) & (close > close.shift(-1))
assert local_high_after_next.iloc[2]
print("事后局部高点不可原时刻直接交易", local_high_after_next.tolist())


if "lab" in globals():
    lab = globals()["lab"]
    lab.table(result, title="突破状态逐行核对")
    lab.lines({"收盘": close, "此前上沿": upper, "此前下沿": lower}, title="历史区间与突破")
