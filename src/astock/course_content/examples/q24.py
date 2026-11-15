import pandas as pd
import numpy as np
bars = pd.DataFrame({"high":[11.,12.,13.,12.,11.,13.],
                     "low":[9.,10.,11.,9.,8.,10.],
                     "close":[10.,11.,12.,10.,9.,12.]})
n=3
highest=bars["high"].rolling(n,min_periods=n).max()
lowest=bars["low"].rolling(n,min_periods=n).min()
width=highest-lowest
rsv=(100*(bars["close"]-lowest)/width.replace(0,np.nan))
k_values=np.full(len(bars),np.nan)
d_values=np.full(len(bars),np.nan)
k=d=50.
for i,value in enumerate(rsv):
    if pd.isna(value):
        continue
    k=2*k/3+value/3
    d=2*d/3+k/3
    k_values[i],d_values[i]=k,d
j_values=3*k_values-2*d_values
print(bars.assign(RSV=rsv,K=k_values,D=d_values,J=j_values).round(4).to_string(index=False))
np.testing.assert_allclose(rsv.iloc[2],75)
np.testing.assert_allclose(k_values[2],58.33333333333333)
np.testing.assert_allclose(d_values[2],52.77777777777777)
np.testing.assert_allclose(j_values[2],69.44444444444444)
assert np.isnan(k_values[:2]).all()


if "lab" in globals():
    lab = globals()["lab"]
    lab.table(bars.assign(RSV=rsv, K=k_values, D=d_values, J=j_values), title="KDJ 递推数值")
    lab.lines({"K": k_values, "D": d_values, "J": j_values}, title="KDJ 与预热缺失")
