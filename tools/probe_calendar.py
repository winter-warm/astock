"""Compare supported exchange announcements with the independently downloaded Sina calendar."""
from datetime import timedelta
import json
from pathlib import Path

from astock.trading_calendar import END, START, manifest, trading_day


def main():
    import akshare as ak
    from akshare.utils.context import config
    config.timeout = (5, 15)
    frame = ak.tool_trade_date_hist_sina()
    days = set(frame.trade_date)
    first, last = min(days), max(days)
    start, end = max(first, START), min(last, END)
    at, mismatches, checked = start, [], 0
    while at <= end:
        if trading_day(at) != (at in days):
            mismatches.append(at.isoformat())
        checked += 1
        at += timedelta(days=1)
    result = {"source": "AKShare / 新浪历史交易日历", "source_first": first.isoformat(), "source_last": last.isoformat(),
              "compared_start": start.isoformat(), "compared_end": end.isoformat(), "days_checked": checked,
              "mismatches": mismatches, "calendar": manifest(), "passed": not mismatches and checked > 0}
    root = Path("output/calendar-016")
    root.mkdir(parents=True, exist_ok=True)
    (root / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
