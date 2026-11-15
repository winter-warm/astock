"""时间序列验证：标签跨5期，训练与验证之间留出边界。"""
import numpy as np
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error

rng = np.random.default_rng(59)
n, horizon = 180, 5
r = rng.normal(0, .01, n + horizon)
X = np.column_stack([r[:n], np.roll(r[:n], 1)])
X[0, 1] = 0
y = np.array([np.prod(1+r[t+1:t+horizon+1])-1 for t in range(n)])
splitter = TimeSeriesSplit(n_splits=3, test_size=30, gap=horizon)
errors = []
for fold, (tr, va) in enumerate(splitter.split(X)):
    assert tr.max() + horizon < va.min()
    model = make_pipeline(StandardScaler(), Ridge(alpha=10.))
    model.fit(X[tr], y[tr])
    np.testing.assert_allclose(model.named_steps["standardscaler"].mean_, X[tr].mean(axis=0))
    error = mean_squared_error(y[va], model.predict(X[va]))
    errors.append(error)
    print(f"折{fold}: 训练{tr[0]}—{tr[-1]}, 验证{va[0]}—{va[-1]}, MSE={error:.8f}")
assert len(errors) == 3
assert np.isfinite(errors).all()

