from io import StringIO
import pandas as pd

raw = """symbol,date,close
000001.SZ,2026-01-06,10.2
000001.SZ,2026-01-05,10.0
000001.SZ,2026-01-05,10.0
000001.SZ,not-a-date,11.0
"""
frame = pd.read_csv(StringIO(raw), dtype={"symbol": "string"})
frame["date"] = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="coerce")
rejected = frame.loc[frame["date"].isna()].copy()
valid = frame.loc[frame["date"].notna()].copy()
valid["close"] = pd.to_numeric(valid["close"], errors="raise")
assert (valid["close"] > 0).all()
conflicts = valid.groupby(["symbol", "date"])["close"].nunique()
assert not (conflicts > 1).any(), "同一证券时刻价格冲突，不能随意保留最后一行"
clean = valid.drop_duplicates(["symbol", "date"]).sort_values(["symbol", "date"])
print("隔离行数", len(rejected))
print(clean.to_string(index=False))
assert len(rejected) == 1
assert clean["close"].tolist() == [10.0, 10.2]
assert clean["symbol"].iloc[0] == "000001.SZ"

