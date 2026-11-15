import pandas as pd
import numpy as np
import hashlib
import json

# 人工除息案例：每股分红 0.2，忽略税费，不是实际证券数据。
raw = pd.Series([10.0, 9.8], name="raw_close")
cash_per_share = .2
price_return = raw.iloc[1] / raw.iloc[0] - 1
economic_return = (raw.iloc[1] + cash_per_share) / raw.iloc[0] - 1
factor = pd.Series([.98, 1.0])
adjusted = raw * factor
shares = 100
value_before = shares * raw.iloc[0]
value_after = shares * raw.iloc[1] + shares * cash_per_share
print("未复权价格收益", round(price_return, 4))
print("计入分红的持有收益", round(economic_return, 4))
print("示意复权序列", adjusted.tolist())
np.testing.assert_allclose(price_return, -.02)
np.testing.assert_allclose(economic_return, 0)
np.testing.assert_allclose(value_before, value_after)
manifest = {"kind": "synthetic", "unit": "yuan/share", "adjustment": "illustrative",
            "observations": raw.tolist(), "cash_per_share": cash_per_share}
encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
print("样本摘要", hashlib.sha256(encoded).hexdigest())

