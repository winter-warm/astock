import numpy as np
import pandas as pd

def rsi_wilder(values, period=3):
    values = np.asarray(values, dtype=float)
    if period < 1:
        raise ValueError("period 必须为正整数")
    result = np.full(len(values), np.nan)
    if len(values) <= period:
        return result
    delta = np.diff(values)
    gain = np.maximum(delta, 0)
    loss = np.maximum(-delta, 0)
    avg_gain = gain[:period].mean()
    avg_loss = loss[:period].mean()
    def score(gain_mean, loss_mean):
        if gain_mean == 0 and loss_mean == 0:
            return 50.0  # 本课明确的全平盘约定
        if loss_mean == 0:
            return 100.0
        return 100.0 * gain_mean / (gain_mean + loss_mean)
    result[period] = score(avg_gain, avg_loss)
    for i in range(period+1, len(values)):
        avg_gain = ((period-1)*avg_gain+gain[i-1])/period
        avg_loss = ((period-1)*avg_loss+loss[i-1])/period
        result[i] = score(avg_gain, avg_loss)
    return result

close = [10,11,10,12,11,13]
result = rsi_wilder(close)
print(pd.DataFrame({"close":close, "RSI3":result}).to_string(index=False))
np.testing.assert_allclose(result[3:], [75, 54.54545454545455, 75])
assert np.isnan(result[:3]).all()
np.testing.assert_allclose(rsi_wilder([7]*8)[3:],50)
np.testing.assert_allclose(rsi_wilder(range(1,9))[3:],100)
np.testing.assert_allclose(rsi_wilder(range(9,1,-1))[3:],0)


if "lab" in globals():
    lab = globals()["lab"]
    lab.table(pd.DataFrame({"close": close, "RSI3": result}), title="RSI 手算核对")
    lab.lines({"RSI3": result}, title="涨跌幅度的相对强弱")
