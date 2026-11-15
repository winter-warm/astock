"""Streaming coverage diagnostics. Missing observations are never synthesized."""
from collections import defaultdict
from datetime import datetime, time, timedelta
from functools import lru_cache
from html import escape
from pathlib import Path
import json

from astock.domain import Bar, CN, Quote
from astock.rules import continuous_close, rule_at
from astock.trading_calendar import END, START, manifest, trading_day

VERSION = "coverage-v3"
LABELS = {"missing_day": "交易日无记录", "missing_bar": "分钟柱缺口", "outside_range": "超出请求范围",
          "before_coverage": "开头未覆盖", "after_coverage": "末尾未覆盖", "closed_day": "休市日记录",
          "outside_session": "不参与连续竞价撮合", "suspended": "已标记停牌", "unknown_calendar": "日历未覆盖",
          "state_suspended": "资料确认整日停牌", "unlisted": "未上市或已摘牌", "unknown_rule": "证券状态未覆盖"}


@lru_cache(maxsize=32)
def expected_minutes(period, sh_etf):
    if period not in {"1m", "5m", "15m", "30m", "60m"}:
        return ()
    step = int(period[:-1])
    return tuple(range(570 + step, 691, step)) + tuple(range(780 + step, (900 if sh_etf else 897) + 1, step))


def bound(value, *, end=False):
    if len(value) == 10:
        return datetime.combine(datetime.fromisoformat(value).date(), time.max if end else time.min, CN)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("数据覆盖范围须使用日期或含时区的时间")
    return parsed.astimezone(CN)


class CoverageScan:
    def __init__(self, meta, *, details=False):
        self.meta, self.keep_details = meta, details
        self.teaching = bool(meta.get("demo"))
        self.by_symbol = defaultdict(dict)
        self.limits = {}
        self.counts = defaultdict(int)
        self.detail_rows = []
        self.first = self.last = None
        self.quote_count = 0

    def detail(self, kind, symbol, start, end, count, unit="条"):
        self.counts[kind] += count
        if self.keep_details:
            self.detail_rows.append({"kind": kind, "symbol": symbol, "start": start, "end": end,
                                     "count": count, "unit": unit})

    def accept(self, event):
        if isinstance(event, Quote):
            self.quote_count += 1
            return
        if not isinstance(event, Bar):
            return
        at = event.time.astimezone(CN)
        self.first = min(self.first, at) if self.first else at
        self.last = max(self.last, at) if self.last else at
        low, high = self.limits.get(event.symbol, (at, at))
        self.limits[event.symbol] = (min(low, at), max(high, at))
        rule = self.meta["rules"][event.symbol]
        day = at.date()
        old = self.by_symbol[event.symbol].get(day, 0)
        minute = at.hour * 60 + at.minute
        minute_period = event.period != "1d"
        if not minute_period:
            self.by_symbol[event.symbol][day] = 1
        elif (not at.second and not at.microsecond
              and minute in expected_minutes(event.period, continuous_close(day.isoformat(), rule) == time(15))):
            self.by_symbol[event.symbol][day] = old | (1 << minute)
        else:
            self.by_symbol[event.symbol][day] = old
            self.detail("outside_session", event.symbol, at.isoformat(), at.isoformat(), 1)
        day_state = trading_day(day, teaching=self.teaching)
        if day_state is None:
            self.counts["unknown_calendar_records"] += 1
        if day_state is False:
            self.detail("closed_day", event.symbol, at.isoformat(), at.isoformat(), 1)
        if event.suspended:
            self.detail("suspended", event.symbol, at.isoformat(), at.isoformat(), 1)

    def finish(self):
        report = {"version": VERSION, "dataset_id": self.meta["id"], "dataset_sha256": self.meta.get("sha256", ""),
                  "dataset_name": self.meta["name"], "calendar": manifest(self.teaching), "counts": {},
                  "actions_verified": bool(self.meta.get("corporate_actions_verified")),
                  "basis": "请求范围" if self.meta.get("coverage_request") else "数据实际首末时刻",
                  "details": self.detail_rows, "details_complete": self.keep_details,
                  "note": "缺口只表示预期时段没有记录，可能是停牌、未上市或上游未覆盖；须核对原因。指标周期按实际记录计算，不补值。"}
        if self.quote_count:
            report.update({"status": "snapshots", "quote_count": self.quote_count,
                           "note": "快照按实际采样保留，不据 5 秒目标推断完整秒级历史；断流、重复及过期由撮合器逐条处理。"})
            return report
        if not self.first:
            report.update({"status": "empty", "note": "没有 K 线，无法检查覆盖范围。"})
            return report
        request = self.meta.get("coverage_request")
        start, end = (bound(request["start"]), bound(request["end"], end=True)) if request else (self.first, self.last)
        if start > end:
            raise ValueError("数据覆盖范围的起点晚于终点")
        report.update({"start": start.isoformat(), "end": end.isoformat(),
                       "observed_start": self.first.isoformat(), "observed_end": self.last.isoformat()})
        if self.teaching and (end - start).days > 36600:
            raise ValueError("教学数据范围异常，超过 100 年")
        # Count unknown spans in O(1), rather than inventing a holiday calendar
        # or iterating an unbounded user-declared range.
        first_day, last_day = start.date(), end.date()
        if not self.teaching:
            for a, b in ((first_day, min(last_day, START - timedelta(days=1))),
                         (max(first_day, END + timedelta(days=1)), last_day)):
                if a <= b:
                    self.detail("unknown_calendar", "全体", a.isoformat(), b.isoformat(), (b - a).days + 1, "自然日")
            first_day, last_day = max(first_day, START), min(last_day, END)
        period = self.meta["period"]
        for symbol in self.meta["symbols"]:
            rule = self.meta["rules"][symbol]
            observed = self.by_symbol[symbol]
            low, high = self.limits.get(symbol, (None, None))
            if low and (low < start or high > end):
                self.detail("outside_range", symbol, low.isoformat(), high.isoformat(), 1, "标的")
            day = first_day
            while day <= last_day:
                if trading_day(day, teaching=self.teaching):
                    state = rule_at(rule, day.isoformat()).status
                    if state in {"suspended", "unlisted"}:
                        self.detail("state_suspended" if state == "suspended" else "unlisted",
                                    symbol, day.isoformat(), day.isoformat(), 1, "交易日")
                        day += timedelta(days=1)
                        continue
                    if state == "unknown" and rule.history:
                        self.detail("unknown_rule", symbol, day.isoformat(), day.isoformat(), 1, "交易日")
                    minutes = (900,) if period == "1d" else expected_minutes(period, continuous_close(day.isoformat(), rule) == time(15))
                    expected = [datetime.combine(day, time(m // 60, m % 60), CN) for m in minutes]
                    expected = [at for at in expected if start <= at <= end]
                    if expected:
                        if day not in observed:
                            self.detail("missing_day", symbol, day.isoformat(), day.isoformat(), 1, "交易日")
                        missing = [at for at in expected if not observed.get(day, 0) or (
                            period != "1d" and not observed[day] & (1 << (at.hour * 60 + at.minute)))]
                        groups = []
                        for at in missing:
                            kind = "before_coverage" if low and at < low else "after_coverage" if high and at > high else "missing_bar"
                            if period == "1d" and kind == "missing_bar":
                                continue  # The missing_day row already describes this exact gap.
                            if (groups and groups[-1][0] == kind and period != "1d"
                                    and (at - groups[-1][2]).total_seconds() == int(period[:-1]) * 60):
                                groups[-1][2], groups[-1][3] = at, groups[-1][3] + 1
                            else:
                                groups.append([kind, at, at, 1])
                        for kind, a, b, count in groups:
                            self.detail(kind, symbol, a.isoformat(), b.isoformat(), count, "根 K 线")
                        self.counts["expected_bars"] += len(expected)
                        self.counts["missing_bars_total"] += len(missing)
                day += timedelta(days=1)
        report["counts"] = dict(self.counts)
        report["status"] = "review" if any(self.counts[key] for key in (
            "missing_bars_total", "unknown_calendar", "closed_day", "outside_range", "unknown_rule")) else "checked"
        if not report["actions_verified"]:
            report["status"] = "blocked_actions"
        return report


def coverage_text(report):
    if not report:
        return "覆盖范围尚未检查"
    if report["status"] in ("snapshots", "empty"):
        return report["note"]
    counts = report["counts"]
    parts = ["教学虚拟日历" if report["calendar"]["version"].startswith("synthetic") else "交易所日历检查"]
    parts.append(f"缺少 {counts.get('missing_bars_total', 0):,} 根 K 线")
    for key in ("missing_day", "unknown_calendar", "closed_day", "outside_session", "suspended", "outside_range",
                "state_suspended", "unlisted", "unknown_rule"):
        if counts.get(key):
            parts.append(f"{LABELS[key]} {counts[key]:,}")
    if not report["actions_verified"]:
        parts.append("权益资料未核对，不能回测")
    return " · ".join(parts)


def write_coverage_files(stage, report):
    stage = Path(stage)
    stage.mkdir(parents=True, exist_ok=True)
    (stage / "quality.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = "".join("<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in (
        LABELS[row["kind"]], row["symbol"], row["start"], row["end"], str(row["count"]) + row["unit"])) + "</tr>"
                   for row in report["details"])
    page = f"""<!doctype html><meta charset="utf-8"><title>AStock 数据覆盖检查</title>
    <style>body{{font:15px 'Microsoft YaHei',sans-serif;max-width:1200px;margin:35px auto;padding:20px;background:#101927;color:#e6edf5}}
    table{{border-collapse:collapse;width:100%}}td,th{{padding:10px;border-bottom:1px solid #344357;text-align:left}}pre{{white-space:pre-wrap}}</style>
    <h1>{escape(report['dataset_name'])} · 数据覆盖检查</h1><p>{escape(coverage_text(report))}</p>
    <p>{escape(report['note'])}</p><p>检查依据：{escape(report['basis'])}；{escape(report.get('start', ''))} 至 {escape(report.get('end', ''))}</p>
    <p>以下列出全部 {len(report['details']):,} 处记录。记录时间为 K 线结束时刻；一处区间可包含多根缺失柱。</p>
    <table><tr><th>类型</th><th>证券</th><th>起始</th><th>结束</th><th>数量</th></tr>{rows}</table>
    <h2>检查版本与日历来源</h2><pre>{escape(json.dumps({k: report[k] for k in ('version', 'dataset_id', 'dataset_sha256', 'calendar')}, ensure_ascii=False, indent=2))}</pre>"""
    (stage / "quality.html").write_text(page, encoding="utf-8")


def publish_coverage(root, request, report):
    root = Path(root) / "reports" / "data-quality"
    root.mkdir(parents=True, exist_ok=True)
    name = report["dataset_id"] + "-" + report["dataset_sha256"][:12] + "-" + report["calendar"]["sha256"][:8] + "-" + VERSION
    for extension in ("json", "html"):
        (Path(request["stage"]) / f"quality.{extension}").replace(root / f"{name}.{extension}")
    return root / f"{name}.html"
