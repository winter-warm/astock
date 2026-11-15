import numpy as np
strategy = np.array([.02, -.01, .03, -.02])
benchmark = np.array([.01, 0., .02, -.01])
nav = np.concatenate(([1.], np.cumprod(1 + strategy)))
base = np.concatenate(([1.], np.cumprod(1 + benchmark)))
difference_pp = (nav[-1] - base[-1]) * 100
relative = nav[-1] / base[-1] - 1
print("策略净值", nav)
print("基准净值", base)
print("收益差百分点", difference_pp, "相对净值收益", relative)
np.testing.assert_allclose(nav[-1], 1.01929212)
annual_if_full_year = nav[-1] ** (252 / 4) - 1
print("仅示范错误外推会得到多大数字", annual_if_full_year)
assert annual_if_full_year > nav[-1] - 1
# 两年累计21%，等效复合年增长率10%。
np.testing.assert_allclose(1.21 ** (1 / 2) - 1, .1)

