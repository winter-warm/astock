from __future__ import annotations

import time
from pathlib import Path

from astock.domain import dumps, now_cn
from astock.market import TencentProvider
from astock.rules import continuous_session, default_rule


def summarize_market(samples, symbols, elapsed):
    """Evaluate observed coverage, not merely successful HTTP responses."""
    expected = set(symbols)
    complete = []
    for sample in samples:
        quotes = sample.get("quotes", [])
        names = [q["symbol"] for q in quotes]
        complete.append(bool(sample["ok"] and len(names) == len(expected) and set(names) == expected))
    intervals = [b["offset_seconds"] - a["offset_seconds"] for a, b in zip(samples, samples[1:])]
    span = samples[-1]["offset_seconds"] - samples[0]["offset_seconds"] if samples else 0
    statistics = {}
    for symbol in symbols:
        rows = [next((q for q in s.get("quotes", []) if q["symbol"] == symbol), None) for s in samples]
        ages = [q["age"] for q in rows if q is not None]
        fresh = sum(q is not None and 0 <= q["age"] <= 15 for q in rows)
        statistics[symbol] = {
            "received": sum(q is not None for q in rows),
            "missing": sum(q is None for q in rows),
            "min_age_seconds": min(ages, default=None),
            "max_age_seconds": max(ages, default=None),
            "fresh_ratio": fresh / max(1, len(samples)),
            "advanced_ratio": sum(q is not None and q["advanced"] for q in rows[1:]) / max(1, len(samples) - 1),
        }
    errors = sum(not ok for ok in complete)
    passed = bool(samples) and all(complete) and all(s["in_session"] for s in samples)
    passed = passed and span >= 3600 and bool(intervals) and max(intervals) <= 15
    passed = passed and all(s["fresh_ratio"] == 1 and s["advanced_ratio"] >= .95 for s in statistics.values())
    ages = [q["age"] for s in samples for q in s.get("quotes", [])]
    return {
        "connectivity_passed": any(complete), "one_hour_session_passed": passed,
        "session_check_status": "passed" if passed else "pending_or_failed",
        "reason": "已满足连续开市一小时采集条件" if passed else "未完成连续开市一小时且全部标的覆盖、刷新间隔和数据新鲜度合格的采集",
        "elapsed_seconds": elapsed, "observed_span_seconds": span,
        "samples": samples, "errors": errors, "error_rate": errors / max(1, len(samples)),
        "max_age": max(ages, default=None), "symbols": statistics,
        "refresh_interval_seconds": {"values": intervals, "max": max(intervals, default=None),
                                     "mean": sum(intervals) / len(intervals) if intervals else None},
        "criteria": {"minimum_span_seconds": 3600, "maximum_interval_seconds": 15,
                     "minimum_age_seconds": 0, "maximum_age_seconds": 15, "minimum_advanced_ratio": .95,
                     "required_symbols": symbols, "maximum_error_rate": 0},
    }


def validate_market(root, minutes=0):
    """Reports connectivity separately from a completed in-session stability check."""
    root = Path(root)
    directory = root / "reports"
    directory.mkdir(parents=True, exist_ok=True)
    samples = []
    provider = TencentProvider()
    symbols = ["600000.SH", "000001.SZ", "510300.SH", "159915.SZ"]
    started = time.monotonic()
    deadline = started + max(0, minutes) * 60
    previous = {}
    while True:
        begin = time.monotonic()
        at = now_cn()
        sample = {"time": at, "offset_seconds": begin - started,
                  "in_session": all(continuous_session(at, default_rule(s)) for s in symbols)}
        try:
            quotes = provider.quotes(symbols)
            sample.update({"ok": True, "latency": time.monotonic() - begin,
                           "quotes": [{"symbol": q.symbol, "time": q.time, "last": q.last,
                                       "age": (now_cn() - q.time).total_seconds(),
                                       "advanced": q.time > previous.get(q.symbol, q.time),
                                       "bid": q.bid, "ask": q.ask, "upper": q.upper, "lower": q.lower}
                                      for q in quotes]})
            previous.update({q.symbol: q.time for q in quotes})
        except Exception as e:
            sample.update({"ok": False, "error": str(e)})
        samples.append(sample)
        if minutes <= 0 or begin >= deadline:
            break
        # 盘后不运行一个小时却误标为盘中验收；立即产生待验收报告。
        if not sample["in_session"]:
            break
        time.sleep(max(.1, 5 - (time.monotonic() - begin)))
    elapsed = time.monotonic() - started
    report = summarize_market(samples, symbols, elapsed)
    path = directory / ("market-validation-" + now_cn().strftime("%Y%m%d-%H%M%S") + ".json")
    path.write_text(dumps(report), encoding="utf-8")
    return str(path)
