"""Actual minute bars with provider units and a fixed prior-session reference."""
from datetime import date, datetime, timedelta
import hashlib

from astock.domain import Bar, CN, dec, now_cn
from astock.trading_calendar import trading_day


SOURCES = {"sina": "新浪 · 近期分钟", "eastmoney": "东方财富 · 近期分钟"}


def source_error(error, source):
    if type(error).__name__ == "Push2RateLimitError":
        return "东方财富接口连接被中断，原因尚未确认；可切换新浪分钟源或稍后重试。"
    return f"{SOURCES.get(source, source)}：{error}"


def normalize_time(value):
    result = datetime.fromisoformat(str(value))
    return result.replace(tzinfo=CN) if result.tzinfo is None else result.astimezone(CN)


def frame_hash(frame):
    return hashlib.sha256(frame.to_json(orient="records", date_format="iso", force_ascii=False).encode("utf-8")).hexdigest()


def previous_trading_day(day):
    candidate = day - timedelta(days=1)
    for _ in range(40):
        value = trading_day(candidate)
        if value is None:
            return None
        if value:
            return candidate
        candidate -= timedelta(days=1)
    return None


def normalize_minutes(symbol, period, frame, daily, start, end, *, source, observed=None, action_dates=None):
    """Daily OHLC beyond the preceding close is never copied into a strategy bar."""
    if source not in SOURCES or period not in {"1m", "5m", "15m", "30m", "60m"}:
        raise ValueError("不支持的分钟来源或周期")
    if frame.empty:
        raise ValueError(f"{symbol} 来源未返回分钟数据")
    start_day, end_day = date.fromisoformat(start), date.fromisoformat(end)
    observed = observed or now_cn()
    raw_times = [normalize_time(value) for value in frame["时间"]]
    if any(b <= a for a, b in zip(raw_times, raw_times[1:])):
        raise ValueError(f"{symbol} 分钟来源含重复或乱序时间，不能重排掩盖问题")
    selected = [(row, at) for row, at in zip(frame.to_dict("records"), raw_times)
                if start_day <= at.date() <= end_day and at <= observed]
    pending = sum(start_day <= at.date() <= end_day and at > observed for at in raw_times)
    if not selected:
        raise ValueError(f"{symbol} 所选日期无已完成分钟柱；来源实际返回 {raw_times[0]:%Y-%m-%d %H:%M}"
                         f" 至 {raw_times[-1]:%Y-%m-%d %H:%M}。请选择近期日期或导入已有数据。")
    daily_rows = {}
    for row in daily.to_dict("records"):
        day = date.fromisoformat(str(row["date"])[:10])
        if day in daily_rows:
            raise ValueError("日线参考数据包含重复日期")
        daily_rows[day] = row
    events, issues, references = [], [], {}
    for row, at in selected:
        day = at.date()
        if day not in references:
            prior_day = previous_trading_day(day)
            prior = daily_rows.get(prior_day)
            reference = dec(prior["close"]) if prior else dec(0)
            if reference <= 0:
                issues.append(f"{symbol} {day} 缺少上一交易日收盘参考；不能用上一分钟或当日收盘代替")
            references[day] = {"day": day.isoformat(), "reference_day": str(prior_day) if prior_day else "",
                               "prev_close": str(reference)}
            if action_dates is not None and day in action_dates:
                issues.append(f"{symbol} {day} 存在权益事件，需补充除权参考价及权益明细后再回测")
        quantity = dec(row["成交量"]) * (1 if source == "sina" else 100)
        if quantity < 0 or quantity != quantity.to_integral_value():
            raise ValueError(f"{symbol} {at} 成交量不是非负整数股/份")
        event = Bar(symbol, at, dec(row["开盘"]), dec(row["最高"]), dec(row["最低"]), dec(row["收盘"]),
                    int(quantity), period, dec(references[day]["prev_close"]))
        if min(event.open, event.high, event.low, event.close) <= 0:
            issues.append(f"{symbol} {at} 存在缺失价格；保留来源数值，不能补造开盘价")
        elif not event.low <= min(event.open, event.close) <= max(event.open, event.close) <= event.high:
            raise ValueError(f"{symbol} {at} OHLC 高低价范围无效")
        events.append(event)
    audit = {"adapter": "minute-bars-v2", "source": "akshare-" + source,
             "received_at": observed.isoformat(), "price_adjustment": "none", "time_label": "bar-end",
             "volume_unit": "share", "source_volume_unit": "share" if source == "sina" else "lot-100",
             "raw_count": len(frame), "raw_start": raw_times[0].isoformat(), "raw_end": raw_times[-1].isoformat(),
             "selected_count": len(events), "unfinished_excluded": pending, "minute_frame_sha256": frame_hash(frame),
             "reference_source": "akshare-tencent-daily", "daily_frame_sha256": frame_hash(daily),
             "references": list(references.values()), "request": {"start": start, "end": end}}
    return events, list(dict.fromkeys(issues)), audit


def fetch_minutes(ak, symbol, rule, period, start, end, source, corporate_lookup):
    if source not in SOURCES or period not in {"1m", "5m", "15m", "30m", "60m"}:
        raise ValueError("请选择有效的分钟行情来源")
    code = symbol[-2:].lower() + symbol[:6]
    if source == "sina":
        frame = ak.stock_zh_a_minute(symbol=code, period=period[:-1], adjust="")
        frame = frame.rename(columns={"day": "时间", "open": "开盘", "high": "最高", "low": "最低",
                                      "close": "收盘", "volume": "成交量", "amount": "成交额"})
    else:
        fn = ak.fund_etf_hist_min_em if rule.kind == "etf" else ak.stock_zh_a_hist_min_em
        frame = fn(symbol=symbol[:6], period=period[:-1], start_date=start + " 09:30:00",
                   end_date=end + " 15:00:00", adjust="")
    if frame.empty:
        raise ValueError(f"{symbol} 来源未返回分钟数据，请换用其他来源或近期日期")
    observed = now_cn()
    selected_days = [normalize_time(value).date() for value in frame["时间"]
                     if date.fromisoformat(start) <= normalize_time(value).date() <= date.fromisoformat(end)
                     and normalize_time(value) <= observed]
    if not selected_days:
        # Produce the same helpful actual-coverage error without a pointless daily request.
        import pandas as pd
        return normalize_minutes(symbol, period, frame, pd.DataFrame(), start, end, source=source, observed=observed)
    issues = []
    try:
        daily = ak.stock_zh_a_hist_tx(symbol=code, start_date=(min(selected_days) - timedelta(days=40)).isoformat(),
                                     end_date=max(selected_days).isoformat(), adjust="")
    except Exception as error:
        import pandas as pd
        daily = pd.DataFrame()
        issues.append(f"{symbol} 昨收参考获取失败：{error}")
    try:
        actions = set(corporate_lookup(symbol))
    except Exception as error:
        actions = None
        issues.append(f"{symbol} 无法核对权益因子：{error}")
    events, problems, audit = normalize_minutes(symbol, period, frame, daily, start, end,
                                               source=source, observed=observed, action_dates=actions)
    # Rights between observed dates also matter when no minute rows exist on the ex-date.
    if actions:
        for day in actions:
            if min(selected_days) <= day <= max(selected_days):
                issues.append(f"{symbol} 区间内存在权益事件 {day}，需补充权益明细")
    audit["corporate_dates_checked"] = actions is not None
    audit["corporate_dates_in_range"] = sorted(str(d) for d in (actions or ()) if min(selected_days) <= d <= max(selected_days))
    return events, list(dict.fromkeys(issues + problems)), audit
