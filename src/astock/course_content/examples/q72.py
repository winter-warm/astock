"""毕业项目参考：完整时间边界、模型选择、成本和研究报告。"""
from pathlib import Path
import hashlib
import json
import platform
from importlib.metadata import version
import numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error


rng = np.random.default_rng(72)
returns = np.zeros(650)
for t in range(1, len(returns)):
    returns[t] = .15*returns[t-1] + rng.normal(0, .01)
times = np.arange(20, len(returns)-1)
X = np.array([[returns[t], returns[t-4:t+1].mean(), returns[t-19:t+1].std()]
              for t in times])
y = returns[times+1]
tr, va, te = slice(0, 350), slice(351, 480), slice(481, None)
assert times[349]+1 < times[351] and times[479]+1 < times[481]
models = {"ridge": make_pipeline(StandardScaler(), Ridge(alpha=10.)),
          "forest": RandomForestRegressor(n_estimators=30, max_depth=3,
                                          min_samples_leaf=25, random_state=72, n_jobs=1)}
for model in models.values():
    model.fit(X[tr], y[tr])
validation = {name: mean_squared_error(y[va], model.predict(X[va])) for name, model in models.items()}
winner = min(validation, key=validation.get)
prediction = models[winner].predict(X[te])
position = (prediction > 0).astype(float)*.5
turnover = np.abs(np.diff(np.r_[0., position]))
gross = position*y[te]
net = gross-.001*turnover
curve = np.r_[1., np.cumprod(1+net)]
drawdown = curve/np.maximum.accumulate(curve)-1
report = {
    "data_kind": "synthetic", "seed": 72, "python": platform.python_version(),
    "dependency_versions": {name: version(name) for name in ("numpy", "scikit-learn")},
    "feature_names": ["ret_1", "mean_5", "std_20"], "horizon": 1,
    "train_rows": [0, 350], "validation_rows": [351, 480], "test_rows": [481, len(X)],
    "data_sha256": hashlib.sha256(returns.tobytes()).hexdigest(),
    "candidate_validation_mse": validation, "frozen_model": winner,
    "test_mse": mean_squared_error(y[te], prediction),
    "constant_test_mse": mean_squared_error(y[te], np.full(len(y[te]), y[tr].mean())),
    "research_return": float(curve[-1]-1), "max_drawdown": float(drawdown.min()),
    "traded_notional": float(turnover.sum()), "cost_rate": .001,
    "limitations": ["人工样本不能证明真实盈利", "抽象下一期收益不等于真实撮合",
                    "没有历史证券集合与权益事件", "测试只有一个时间段"],
}
Path("graduation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
assert np.allclose(gross-net, .001*turnover)
assert report["max_drawdown"] <= 0 and np.isfinite(curve).all()
changed = returns.copy()
changed[times[te][0]+1:] = 999
X2 = np.array([[changed[t], changed[t-4:t+1].mean(), changed[t-19:t+1].std()] for t in times])
np.testing.assert_allclose(X2[tr], X[tr])
np.testing.assert_allclose(X2[va], X[va])
print(json.dumps(report, ensure_ascii=False, indent=2))
print("已写入 graduation_report.json；这是人工数据研究报告，不是实盘验收。")

