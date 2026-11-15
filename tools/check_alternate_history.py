import sys
from pathlib import Path
import akshare as ak
from astock.domain import dumps

sys.stdout.reconfigure(encoding="utf-8")
results = []
for symbol in ("sh510300", "sh600000"):
    item = {"symbol": symbol}
    try:
        frame = ak.stock_zh_a_hist_tx(symbol=symbol, start_date="20261102", end_date="20261113", adjust="")
        item["history_count"] = len(frame)
        item["columns"] = list(frame.columns)
        item["example"] = str(frame.head(2).to_dict("records"))
    except Exception as e:
        item["history_error"] = str(e)
    try:
        factors = ak.stock_zh_a_daily(symbol=symbol, adjust="hfq-factor")
        item["factors_count"] = len(factors)
        item["factors_example"] = str(factors.head(3).to_dict("records"))
    except Exception as e:
        item["factors_error"] = str(e)
    results.append(item)
    print(item)
root = Path("output/history-check")
root.mkdir(parents=True, exist_ok=True)
(root / "alternate-probe.json").write_text(dumps(results), encoding="utf-8")
