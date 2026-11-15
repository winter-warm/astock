from pathlib import Path
import csv

path = Path("prices.csv")
with path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=["证券", "收盘"])
    writer.writeheader()
    writer.writerow({"证券": "教学标的", "收盘": 10.5})

with path.open(encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle))
price = float(rows[0]["收盘"])
print(rows[0]["证券"], price * 100)
assert price == 10.5

