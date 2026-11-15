import numpy as np
equity = np.array([100., 110., 88., 99., 111.])
peak = np.maximum.accumulate(equity)
drawdown = equity / peak - 1
maximum_drawdown = -drawdown.min()
returns = equity[1:] / equity[:-1] - 1
excess = returns - 0.0001  # 人工设定每期参考收益，不是市场报价
vol = excess.std(ddof=1)
sharpe_per_period = excess.mean() / vol if vol > 0 else np.nan
print("历史峰值", peak)
print("回撤", drawdown)
print("最大回撤", maximum_drawdown, "单期夏普", sharpe_per_period)
np.testing.assert_allclose(drawdown, [0, 0, -.2, -.1, 0])
np.testing.assert_allclose(maximum_drawdown, .2)
assert peak[2] == 110
flat = np.zeros(4)
flat_sharpe = np.nan if flat.std(ddof=1) == 0 else flat.mean() / flat.std(ddof=1)
assert np.isnan(flat_sharpe)

