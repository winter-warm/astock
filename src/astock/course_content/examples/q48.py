import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
prices=10+np.arange(160)*.01+.5*np.sin(np.arange(160)/4)
split=100
def evaluate(values,period,cost):
    p=pd.Series(values)
    target=(p>p.rolling(period,min_periods=period).mean()).astype(float)
    held=target.shift(1,fill_value=0)*.5
    turnover=held.diff().abs().fillna(held.iloc[0])
    net=held*p.pct_change(fill_method=None).fillna(0)-turnover*cost
    equity=np.r_[1.,(1+net).cumprod().to_numpy()]
    return {"return":float(equity[-1]-1),
            "drawdown":float((1-equity/np.maximum.accumulate(equity)).max()),
            "turnover":float(turnover.sum())}
candidates={n:evaluate(prices[:split],n,.001) for n in [3,5,10]}
chosen=max(candidates,key=lambda n:candidates[n]["return"])
report={"data_kind":"synthetic","sha256":hashlib.sha256(prices.tobytes()).hexdigest(),
        "split":split,"chosen_period":chosen,"train":candidates,
        "test":evaluate(prices[split:],chosen,.001),
        "stress":evaluate(prices[split:],chosen,.005),
        "limitation":"简化目标权重研究，非A股真实撮合，不是盈利证据"}
Path("research-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False,indent=2))
assert report["stress"]["return"]<=report["test"]["return"]
assert report["test"]["drawdown"]>=0

