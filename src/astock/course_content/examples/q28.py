import pandas as pd
close=pd.Series([10.,10.2,10.1,10.5,10.8,10.4,10.9,11.2,10.7,11.3])
volume=pd.Series([100,110,90,120,160,100,170,180,110,190],dtype=float)
fast=close.rolling(2,min_periods=2).mean()
slow=close.rolling(4,min_periods=4).mean()
trend=(fast>slow)&slow.notna()
redundant=(fast-slow>0)&slow.notna()  # 同一信息换个写法
volume_filter=volume>volume.rolling(3,min_periods=3).mean().shift(1)
combined=trend&volume_filter
print(pd.DataFrame({"close":close,"trend":trend,"same_trend":redundant,
                    "volume_filter":volume_filter,"combined":combined}).to_string())
assert trend.equals(redundant)
assert combined.sum() <= trend.sum()
def causal_signal(c,v):
    f=c.rolling(2,min_periods=2).mean()
    s=c.rolling(4,min_periods=4).mean()
    return ((f>s)&s.notna()) & (v>v.rolling(3,min_periods=3).mean().shift(1))
changed=close.copy()
changed.iloc[7:]=[100,50,200]
pd.testing.assert_series_equal(causal_signal(changed,volume).iloc[:7],combined.iloc[:7])
print("基础信号次数",int(trend.sum()),"过滤后",int(combined.sum()))


if "lab" in globals():
    lab = globals()["lab"]
    lab.table(pd.DataFrame({"close": close, "trend": trend,
                            "volume_filter": volume_filter, "combined": combined}), title="条件组合逐行比较")
    lab.lines({"趋势状态": trend.astype(int), "组合状态": combined.astype(int)}, title="条件筛选前后")
