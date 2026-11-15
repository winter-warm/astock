"""训练集拟合预处理；未来分布变化不重写历史尺度。"""
import numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge

rng = np.random.default_rng(56)
X = rng.normal(size=(200, 3))
y = .4*X[:, 0] - .2*X[:, 1] + rng.normal(0, .1, 200)
X[140:] += 5
train = slice(0, 120)
test = slice(140, 200)
model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
model.fit(X[train], y[train])
scaler = model.named_steps["standardscaler"]
np.testing.assert_allclose(scaler.mean_, X[train].mean(axis=0))
prediction = model.predict(X[test])
mean_before = scaler.mean_.copy()
X[140:] += 100
np.testing.assert_array_equal(scaler.mean_, mean_before)
assert prediction.shape == (60,)
assert np.isfinite(prediction).all()
wrong_mean = X.mean(axis=0)
print("训练均值：", mean_before.round(4))
print("错误的全样本均值：", wrong_mean.round(4))
print("训练缩放器未受测试数据修改影响：通过")

