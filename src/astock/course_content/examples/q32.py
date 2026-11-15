import numpy as np
import pandas as pd
close = pd.Series([12., 11., 10., 9., 8., 9., 10., 11., 10., 12.])
delta = close.diff()
gain = delta.clip(lower=0).rolling(3).mean()
loss = (-delta.clip(upper=0)).rolling(3).mean()
denom = gain + loss
rsi = 100 * gain / denom.where(denom != 0)
rsi = rsi.mask((denom == 0) & denom.notna(), 50)
trend = close > close.rolling(4).mean()
rebound = (rsi.shift(1) < 40) & (rsi >= 40)
filtered = rebound & trend
print(pd.DataFrame(dict(close=close, rsi=rsi, rebound=rebound, trend=trend, filtered=filtered)).round(2))
assert np.isclose(rsi[3], 0)
assert rebound[6] and trend[6] and filtered[6]
assert not filtered[:3].any()

