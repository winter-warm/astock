import pandas as pd
import numpy as np
close=pd.Series([10.,11.,11.,10.,12.])
volume=pd.Series([100,200,300,400,500],dtype=float)
direction=np.sign(close.diff()).fillna(0)
obv=(direction*volume).cumsum()
past_mean=volume.rolling(3,min_periods=3).mean().shift(1)
relative_volume=volume/past_mean
print(pd.DataFrame({"close":close,"volume_shares":volume,"OBV":obv,
                    "past_mean_volume":past_mean,"relative_volume":relative_volume}).to_string())
np.testing.assert_allclose(obv,[0,200,200,-200,300])
np.testing.assert_allclose(relative_volume.iloc[3],2)
np.testing.assert_allclose(relative_volume.iloc[4],500/300)
cumulative=np.array([1000,1300,1300,1800])
increments=np.diff(cumulative,prepend=cumulative[0])
np.testing.assert_allclose(increments,[0,300,0,500])
print("同一会话累计量增量",increments)


if "lab" in globals():
    lab = globals()["lab"]
    lab.table(pd.DataFrame({"close": close, "volume": volume, "OBV": obv,
                            "relative_volume": relative_volume}), title="成交量指标数值")
    lab.lines({"OBV": obv}, title="按收盘方向累计的成交量")
