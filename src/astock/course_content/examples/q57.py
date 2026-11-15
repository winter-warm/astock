import numpy as np
from sklearn.metrics import mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.metrics import accuracy_score, log_loss

rng = np.random.default_rng(55)
r = np.zeros(520)
for t in range(1, len(r)):
    r[t] = .25 * r[t-1] + rng.normal(0, .01)
times = np.arange(5, len(r)-1)
X = np.array([r[t-4:t+1] for t in times])
y = r[times+1]
train, valid, test = slice(0, 300), slice(301, 400), slice(401, None)
assert times[299] + 1 < times[301]

ridge = make_pipeline(StandardScaler(), Ridge(alpha=10.0)).fit(X[train], y[train])
direction = (y > 0).astype(int)
logit = make_pipeline(StandardScaler(), LogisticRegression(C=.2, max_iter=500))
logit.fit(X[train], direction[train])
pred = ridge.predict(X[test])
prob = logit.predict_proba(X[test])[:, 1]
constant = np.full(len(y[test]), y[train].mean())
base_prob = np.full(len(y[test]), direction[train].mean())
print("岭回归MSE", mean_squared_error(y[test], pred))
print("常数MSE", mean_squared_error(y[test], constant))
print("逻辑回归准确率", accuracy_score(direction[test], prob >= .5))
print("逻辑回归logloss", log_loss(direction[test], prob, labels=[0, 1]))
print("基线logloss", log_loss(direction[test], base_prob, labels=[0, 1]))
assert np.all((prob > 0) & (prob < 1))
assert pred.shape == y[test].shape
assert np.isfinite(pred).all()

