import pandas as pd
close = pd.Series([10., 11., 12., 11., 13., 12., 10., 9.])
upper = close.shift(1).rolling(3, min_periods=3).max()
lower = close.shift(1).rolling(3, min_periods=3).min()
position = 0
targets = []
for i, price in close.items():
    if pd.notna(upper[i]):
        if price > upper[i]:
            position = 1
        elif price < lower[i]:
            position = 0
    targets.append(position)
print(pd.DataFrame(dict(close=close, prior_high=upper, prior_low=lower, target=targets)))
assert upper[4] == 12 and targets[4] == 1
assert targets[6] == 0
bad_upper = close.rolling(3).max()
assert not (close > bad_upper).any()

