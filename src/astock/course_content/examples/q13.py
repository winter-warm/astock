import numpy as np
prices = np.array([100., 110., 99.])
simple = prices[1:] / prices[:-1] - 1
logs = np.log(prices[1:] / prices[:-1])
wealth = np.concatenate(([1.], np.cumprod(1 + simple)))
print("简单收益", simple)
print("累计净值", wealth)
print("简单相加", simple.sum(), "复利", wealth[-1] - 1)
np.testing.assert_allclose(simple, [.1, -.1])
np.testing.assert_allclose(wealth[-1], .99)
np.testing.assert_allclose(np.expm1(logs.sum()), -.01)
loss = .2
recovery = 1 / (1 - loss) - 1
print("亏损20%后回本所需收益", recovery)
np.testing.assert_allclose(recovery, .25)

