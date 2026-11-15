import pandas as pd
import numpy as np
close = pd.Series([10.,11.,12.,11.,10.,9.,10.,12.])
fast = close.ewm(span=3,adjust=False).mean()
slow = close.ewm(span=5,adjust=False).mean()
dif = fast-slow
dea = dif.ewm(span=3,adjust=False).mean()
hist = dif-dea
table = pd.DataFrame({"close":close,"DIF":dif,"DEA":dea,"hist":hist,"hist_x2":2*hist})
print(table.round(6).to_string())
np.testing.assert_allclose(dif.iloc[1],1/6)
np.testing.assert_allclose(dea.iloc[1],1/12)
np.testing.assert_allclose(hist.iloc[1],1/12)
np.testing.assert_allclose(table["hist_x2"],2*table["hist"])
constant = pd.Series([10.]*30)
zero = constant.ewm(span=3,adjust=False).mean()-constant.ewm(span=5,adjust=False).mean()
np.testing.assert_allclose(zero,0)


if "lab" in globals():
    lab = globals()["lab"]
    lab.table(table, title="MACD 逐层计算")
    lab.lines({"DIF": dif, "DEA": dea}, title="差值与信号线")
    lab.lines({"柱体": hist, "两倍柱体": 2 * hist}, title="柱体口径对照", bars=True)
