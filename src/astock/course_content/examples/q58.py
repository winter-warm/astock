import numpy as np
from sklearn.metrics import mean_squared_error
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.tree import DecisionTreeRegressor

rng = np.random.default_rng(55)
r = np.zeros(520)
for t in range(1, len(r)):
    r[t] = .25 * r[t-1] + rng.normal(0, .01)
times = np.arange(5, len(r)-1)
X = np.array([r[t-4:t+1] for t in times])
y = r[times+1]
train, valid, test = slice(0, 300), slice(301, 400), slice(401, None)
assert times[299] + 1 < times[301]

models = {
    "tree": DecisionTreeRegressor(max_depth=3, min_samples_leaf=20, random_state=58),
    "forest": RandomForestRegressor(n_estimators=40, max_depth=4, min_samples_leaf=15,
                                    random_state=58, n_jobs=1),
    "boost": HistGradientBoostingRegressor(max_iter=60, max_leaf_nodes=7,
                                          l2_regularization=2., early_stopping=False, random_state=58),
}
validation = {}
for name, model in models.items():
    model.fit(X[train], y[train])
    validation[name] = mean_squared_error(y[valid], model.predict(X[valid]))
winner = min(validation, key=validation.get)
frozen = models[winner]
pred = frozen.predict(X[test])
print("验证误差：", validation)
print("冻结模型：", winner, "测试误差：", mean_squared_error(y[test], pred))
assert pred.shape == y[test].shape
assert np.isfinite(pred).all()
future_changed = y.copy()
future_changed[test] = 999
repeat = min(models, key=lambda name: mean_squared_error(future_changed[valid], models[name].predict(X[valid])))
assert repeat == winner

