import pandas as pd
import numpy as np
close=pd.Series([10.,11.,12.,11.,10.,9.,10.,13.])
n=3
middle=close.rolling(n,min_periods=n).mean()
sigma=close.rolling(n,min_periods=n).std(ddof=0)
upper=middle+2*sigma
lower=middle-2*sigma
bandwidth=(upper-lower)/middle
percent_b=(close-lower)/(upper-lower).replace(0,np.nan)
print(pd.DataFrame({"close":close,"middle":middle,"upper":upper,"lower":lower,
                    "bandwidth":bandwidth,"%B":percent_b}).round(5).to_string())
np.testing.assert_allclose(middle.iloc[2],11)
np.testing.assert_allclose(sigma.iloc[2],np.sqrt(2/3))
np.testing.assert_allclose(upper.iloc[2],11+2*np.sqrt(2/3))
flat=pd.Series([10.]*5)
assert (flat.rolling(3).std(ddof=0).dropna()==0).all()


if "lab" in globals():
    lab = globals()["lab"]
    lab.table(pd.DataFrame({"close": close, "middle": middle, "upper": upper,
                            "lower": lower, "bandwidth": bandwidth, "%B": percent_b}), title="布林带数值")
    lab.lines({"收盘": close, "中轨": middle, "上轨": upper, "下轨": lower}, title="价格与波动带")
