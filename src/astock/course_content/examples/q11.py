import pandas as pd
import numpy as np

close = pd.Series([10., 11., 12., 9., 10., 13.], name="close")
def features(values):
    current_mean = values.rolling(3, min_periods=3).mean()
    previous_mean = current_mean.shift(1)
    signal_at_close = (values > current_mean) & current_mean.notna()
    position_for_next_interval = signal_at_close.shift(1, fill_value=False)
    return pd.DataFrame({"close": values, "ma3": current_mean,
        "prior_ma3": previous_mean, "signal": signal_at_close,
        "lagged_signal": position_for_next_interval})
result = features(close)
print(result.to_string())
np.testing.assert_allclose(result.loc[2, "ma3"], 11)
assert pd.isna(result.loc[2, "prior_ma3"])
np.testing.assert_allclose(result.loc[3, "prior_ma3"], 11)
changed = close.copy()
changed.iloc[4:] = [100, 200]
pd.testing.assert_frame_equal(features(changed).iloc[:4], result.iloc[:4])
bad_centered = close.rolling(3, center=True).mean()
assert bad_centered.loc[1] == 11
print("未来修改不影响前四行：通过；居中窗口不能直接作为当时信号。")

