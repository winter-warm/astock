import numpy as np

# 人工构造：行是观察时刻，列是证券 A、B。
prices = np.array([[10, 20], [11, 18], [12.1, 19.8]], dtype=float)
returns = prices[1:] / prices[:-1] - 1
weights = np.array([0.6, 0.4])
portfolio = returns @ weights
print("形状", prices.shape, returns.shape)
print("逐期收益", returns)
print("固定权重组合收益", portfolio)
np.testing.assert_allclose(returns, [[0.1, -0.1], [0.1, 0.1]])
np.testing.assert_allclose(portfolio, [0.02, 0.1])
view = prices[:2]
snapshot = prices[:2].copy()
view[0, 0] = 99
assert prices[0, 0] == 99
assert snapshot[0, 0] == 10
print("视图会改变原数组；copy 保留独立快照。")

