"""Explicit exchange-calendar coverage; government make-up workdays are not trading days."""
from datetime import date, timedelta
from functools import lru_cache
import hashlib
import json

HOLIDAYS = {
    2023: (("01-01", "01-02"), ("01-21", "01-27"), ("04-05", "04-05"),
           ("04-29", "05-03"), ("06-22", "06-24"), ("09-29", "10-06")),
    2024: (("01-01", "01-01"), ("02-09", "02-17"), ("04-04", "04-06"),
           ("05-01", "05-05"), ("06-10", "06-10"), ("09-15", "09-17"), ("10-01", "10-07")),
    2025: (("01-01", "01-01"), ("01-28", "02-04"), ("04-04", "04-06"),
           ("05-01", "05-05"), ("05-31", "06-02"), ("10-01", "10-08")),
    2026: (("01-01", "01-03"), ("02-15", "02-23"), ("04-04", "04-06"),
           ("05-01", "05-05"), ("06-19", "06-21"), ("09-25", "09-27"), ("10-01", "10-07")),
}
SOURCES = {
    2023: "https://www.szse.cn/disclosure/notice/general/t20221227_598022.html",
    2024: "https://www.szse.cn/disclosure/notice/t20231226_605108.html",
    2025: "https://www.sse.com.cn/disclosure/announcement/general/c/c_20241223_10767108.shtml",
    2026: "https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml",
}
START, END = date(2023, 1, 1), date(2026, 12, 31)
VERSION = "cn-exchange-2023-2026-v1"
DIGEST = hashlib.sha256(json.dumps(HOLIDAYS, sort_keys=True).encode()).hexdigest()


@lru_cache(maxsize=8)
def closed_days(year):
    result = set()
    for first, last in HOLIDAYS[year]:
        current, stop = date.fromisoformat(f"{year}-{first}"), date.fromisoformat(f"{year}-{last}")
        while current <= stop:
            result.add(current)
            current += timedelta(days=1)
    return frozenset(result)


def trading_day(day, *, teaching=False):
    if teaching:
        return day.weekday() < 5
    if day.year not in HOLIDAYS:
        return None  # Unknown, not an inferred weekday session.
    return day.weekday() < 5 and day not in closed_days(day.year)


def manifest(teaching=False):
    if teaching:
        return {"version": "synthetic-weekdays-v1", "source": "教学虚拟日历，仅排除周末", "sha256": ""}
    return {"version": VERSION, "start": START.isoformat(), "end": END.isoformat(), "sha256": DIGEST,
            "sources": {str(key): value for key, value in SOURCES.items()},
            "scope": "沪深交易所普通交易日；不含单证券停牌/上市状态"}
