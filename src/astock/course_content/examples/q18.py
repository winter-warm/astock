import numpy as np
# 每次采用相同名义风险额度的人工交易损益，尚未扣费用。
gross = np.array([20., 20., 20., 20., -100.])
fee = 2.0
net = gross - fee
win_rate = (gross > 0).mean()
avg_win = gross[gross > 0].mean()
avg_loss = -gross[gross < 0].mean()
expectancy = win_rate * avg_win - (1-win_rate) * avg_loss
print("胜率", win_rate, "平均盈利", avg_win, "平均亏损", avg_loss)
print("每笔期望/实际平均", expectancy, gross.mean())
print("扣费总损益", net.sum())
np.testing.assert_allclose(win_rate, .8)
np.testing.assert_allclose(expectancy, -4)
np.testing.assert_allclose(net.sum(), -30)
equity = 10000.
traded_notional = np.array([2000., 3000., 1000.])
one_way_turnover = traded_notional.sum() / equity
cost_rate = .001
print("单边名义换手", one_way_turnover, "简化费用", traded_notional.sum()*cost_rate)
np.testing.assert_allclose(one_way_turnover, .6)
np.testing.assert_allclose(traded_notional.sum()*cost_rate, 6)

