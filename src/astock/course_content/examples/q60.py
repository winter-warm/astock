import numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

rng = np.random.default_rng(55)
r = np.zeros(520)
for t in range(1, len(r)):
    r[t] = .25 * r[t-1] + rng.normal(0, .01)
times = np.arange(5, len(r)-1)
X = np.array([r[t-4:t+1] for t in times])
y = r[times+1]
train, valid, test = slice(0, 300), slice(301, 400), slice(401, None)
assert times[299] + 1 < times[301]

model = make_pipeline(StandardScaler(), LogisticRegression(C=.2, max_iter=500))
model.fit(X[train], (y[train] > 0).astype(int))
pv = model.predict_proba(X[valid])[:, 1]
pt = model.predict_proba(X[test])[:, 1]
fee = .001
def evaluate(probability, realized, threshold):
    target = np.where(probability > threshold, .5, 0.)
    traded = np.abs(np.diff(np.r_[0., target]))
    net = target * realized - fee * traded
    return target, traded, net
thresholds = [.5, .55, .6]
validation = {t: evaluate(pv, y[valid], t)[2].mean() for t in thresholds}
threshold = max(validation, key=validation.get)
position, turnover, net = evaluate(pt, y[test], threshold)
gross = position * y[test]
equity = np.cumprod(1+net)
print("验证阈值比较：", validation)
print("冻结阈值", threshold, "总收益", float(equity[-1]-1),
      "交易名义金额", float(turnover.sum()))
assert np.all((position >= 0) & (position <= .5))
assert np.all(net <= gross + 1e-14)
assert np.isclose((gross-net).sum(), fee*turnover.sum())
assert net.shape == y[test].shape

