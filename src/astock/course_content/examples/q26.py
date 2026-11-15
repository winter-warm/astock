import numpy as np
import pandas as pd

def true_ranges(high, low, close):
    high, low, close = [np.asarray(values, dtype=float) for values in (high, low, close)]
    if not (high.ndim == low.ndim == close.ndim == 1 and len(high) == len(low) == len(close) > 0):
        raise ValueError("高低收必须是等长的非空一维序列")
    if not (np.isfinite([high, low, close]).all() and (low <= close).all() and (close <= high).all()):
        raise ValueError("高低收必须有限且满足 low <= close <= high")
    values = high - low
    for i in range(1, len(close)):
        values[i] = max(values[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
    return values

def wilder_atr(values, period):
    if not isinstance(period, int) or period < 1:
        raise ValueError("周期必须为正整数")
    values = np.asarray(values, dtype=float)
    result = np.full(len(values), np.nan)
    if len(values) < period:
        return result
    result[period-1] = values[:period].mean()
    for i in range(period, len(values)):
        result[i] = ((period-1)*result[i-1] + values[i])/period
    return result

high=np.array([11.,13.,12.,14.,13.])
low=np.array([9.,12.,10.,13.,11.])
close=np.array([10.,12.5,11.,13.5,12.])
tr=true_ranges(high, low, close)  # 首柱缺昨收时取 high-low
n=3
atr=wilder_atr(tr, n)
print(pd.DataFrame({"high":high,"low":low,"close":close,"TR":tr,"ATR3":atr}).to_string(index=False))
np.testing.assert_allclose(tr,[2,3,2.5,3,2.5])
np.testing.assert_allclose(atr[2],2.5)
np.testing.assert_allclose(atr[3],8/3)
risk_budget=1000.
distance=2*atr[-1]
quantity=int(risk_budget/distance)
print("理论份额（尚未按证券单位取整）",quantity,"止损距离",distance)
assert quantity*distance <= risk_budget

# 参数实验同步修改高低收，后一期的前收盘依赖也随之改变。
changed_high, changed_low, changed_close = high.copy(), low.copy(), close.copy()
changed_high[1] += 2
changed_low[1] += 2
changed_close[1] += 2
changed_tr = true_ranges(changed_high, changed_low, changed_close)
np.testing.assert_allclose(changed_tr, [2, 5, 4.5, 3, 2.5])
np.testing.assert_allclose(wilder_atr(changed_tr, 3)[2:], [23/6, 32/9, 173/54])
np.testing.assert_allclose(wilder_atr(tr, 4)[3:], [2.625, 2.59375])
print("合法跳空实验 TR", changed_tr, "ATR", wilder_atr(changed_tr, 3))


if "lab" in globals():
    lab = globals()["lab"]
    lab.table(pd.DataFrame({"close": close, "TR": tr, "ATR3": atr}), title="真实波幅与平滑")
    lab.lines({"TR": tr, "ATR3": atr}, title="跳空幅度进入 ATR")
