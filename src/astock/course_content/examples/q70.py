"""固定验证段选择；最终测试只在冻结后计算。"""
import hashlib
import json
import numpy as np
import pandas as pd

rng = np.random.default_rng(70)
r = rng.normal(.0001, .01, 240)
close = pd.Series(100*np.cumprod(1+r))
future = close.shift(-1)/close-1
validation = slice(100, 170)
test = slice(180, 239)
def score(window, section):
    feature = close/close.shift(window)-1
    target = (feature > 0).astype(float)*.5
    traded = target.diff().abs().fillna(target.abs())
    # Slice labels before calculating returns: candidate evaluation never computes holdout P&L.
    net = target.iloc[section]*future.iloc[section]-.001*traded.iloc[section]
    return float(net.mean())
candidates = [3, 5, 10, 20]
records = [{"window": w, "validation_mean": score(w, validation)} for w in candidates]
winner = max(records, key=lambda row: row["validation_mean"])["window"]
frozen = {"window": winner, "cost": .001, "validation": [100, 170], "test": [180, 239]}
identity = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()
result = {"mode": "offline-synthetic", "all_candidates": records, "frozen_sha256": identity,
          "test_mean": score(winner, test)}
print(json.dumps(result, ensure_ascii=False, indent=2))
assert len(result["all_candidates"]) == 4
assert len(identity) == 64
old = winner
future.iloc[180:] = 999
assert max(candidates, key=lambda w: score(w, validation)) == old

