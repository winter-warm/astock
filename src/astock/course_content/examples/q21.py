import pandas as pd
import numpy as np
close = pd.Series([10.,11.,12.,9.,10.,13.])
sma = close.rolling(3,min_periods=3).mean()
ema = close.ewm(span=3,adjust=False).mean()
manual = [close.iloc[0]]
alpha = 2/(3+1)
for value in close.iloc[1:]:
    manual.append(alpha*value+(1-alpha)*manual[-1])
print(pd.DataFrame({"close":close,"SMA3":sma,"EMA3_seed_first":ema}).to_string())
np.testing.assert_allclose(ema, manual)
np.testing.assert_allclose(ema.iloc[:4], [10,10.5,11.25,10.125])
np.testing.assert_allclose(sma.iloc[2],11)
constant = pd.Series([7.]*10)
np.testing.assert_allclose(constant.ewm(span=3,adjust=False).mean(),7)


if "lab" in globals():
    lab = globals()["lab"]
    lab.table(pd.DataFrame({"close": close, "SMA3": sma, "EMA3": ema}), title="均线数值")
    lab.lines({"收盘": close, "SMA3": sma, "EMA3": ema}, title="简单与指数移动平均")
