"""人工面板：逐期 IC、排名 IC、分组差和换手。"""
import numpy as np
import pandas as pd


scores = np.array([[1, 2, 3, 4], [2, 1, 4, 3], [4, 3, 2, 1]], dtype=float)
future = np.array([[.01, .00, .03, .02], [.02, -.01, .04, .00],
                   [-.03, .02, -.01, .01]])
rows = []
last_weights = np.zeros(4)
for t, (s, y) in enumerate(zip(scores, future)):
    ic = np.corrcoef(s, y)[0, 1]
    rank_ic = pd.Series(s).rank().corr(pd.Series(y).rank())
    order = np.argsort(s, kind="stable")
    weights = np.zeros(4)
    weights[order[-2:]] = .5
    traded_notional = np.abs(weights - last_weights).sum()
    spread = y[order[-2:]].mean() - y[order[:2]].mean()
    rows.append((t, ic, rank_ic, spread, traded_notional))
    last_weights = weights
result = pd.DataFrame(rows, columns=["t", "ic", "rank_ic", "top_minus_bottom", "traded_notional"])
print(result.round(6).to_string(index=False))
assert np.isclose(result.iloc[0].rank_ic, .6)
assert np.isclose(result.iloc[0].top_minus_bottom, .02)
assert np.isclose(result.iloc[0].traded_notional, 1.)
assert (result.traded_notional >= 0).all()
print("平均IC，仅3期不可据此声称显著：", result.ic.mean())

