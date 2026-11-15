"""人工因子组合：只用研究段选组合，测试段不参与。"""
import numpy as np

rng = np.random.default_rng(54)
factors = rng.normal(size=(80, 6, 2))
future = .005 * factors[:, :, 0] - .002 * factors[:, :, 1] + rng.normal(0, .02, (80, 6))
z = (factors - factors.mean(axis=1, keepdims=True)) / factors.std(axis=1, keepdims=True)
candidates = {"equal": np.array([.5, .5]), "first": np.array([1., 0.]),
              "balanced": np.array([.75, .25])}
def portfolio(weights, start, stop):
    score = z[start:stop] @ weights
    selected = np.argsort(score, axis=1)[:, -2:]
    return np.take_along_axis(future[start:stop], selected, axis=1).mean(axis=1)
validation = {name: portfolio(w, 40, 60).mean() for name, w in candidates.items()}
winner = max(validation, key=validation.get)
frozen = candidates[winner].copy()
test = portfolio(frozen, 60, 80)
print("验证段候选：", validation)
print("冻结选择：", winner, "测试均值：", float(test.mean()))
before = frozen.copy()
future[60:] = -100  # 改测试标签不改变已冻结的模型选择。
repeat = max(candidates, key=lambda name: portfolio(candidates[name], 40, 60).mean())
assert repeat == winner
np.testing.assert_array_equal(before, frozen)
assert test.shape == (20,)
assert np.isfinite(test).all()

