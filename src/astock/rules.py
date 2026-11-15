from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP

from astock.domain import CN, InstrumentRule, RulePeriod, dec, symbol_code
from astock.trading_calendar import trading_day

# T+0 仅对明确维护的证券开放；其他 ETF 保守使用 T+1，不从代码推断全部品种。
T0_ETFS = {
    "518880.SH": "黄金ETF", "518800.SH": "黄金基金ETF",
    "513100.SH": "纳指ETF", "513500.SH": "标普500ETF",
    "511010.SH": "国债ETF", "511880.SH": "银华日利ETF",
    "159934.SZ": "黄金ETF", "159920.SZ": "恒生ETF",
}
NAMES = {
    "600000.SH": "浦发银行", "000001.SZ": "平安银行",
    "510300.SH": "沪深300ETF", "159915.SZ": "创业板ETF",
    "510500.SH": "中证500ETF", "588000.SH": "科创50ETF", **T0_ETFS,
}
INDEX_NAMES = {
    "000001.SH": "上证综指", "399001.SZ": "深证成指", "399006.SZ": "创业板指",
    "000300.SH": "沪深300", "000905.SH": "中证500", "000852.SH": "中证1000",
    "000688.SH": "科创50", "000016.SH": "上证50",
}
RULE_SOURCE = "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml"
RULE_CHANGE = "2026-07-06"
RULE_ENGINE_VERSION = "cn-date-rules-v3"
STATUSES = {"normal": "正常交易", "risk_warning": "风险警示 ST / *ST", "no_limit": "无涨跌幅限制",
            "suspended": "停牌", "unlisted": "未上市或已摘牌", "unknown": "规则资料未覆盖"}


def validate_rule(rule):
    if not isinstance(rule, InstrumentRule) or symbol_code(rule.symbol) != rule.symbol:
        raise ValueError("证券规则类型或代码无效")
    if rule.status not in STATUSES or rule.kind not in {"stock", "etf", "index"}:
        raise ValueError("证券规则类别或状态无效")
    if rule.symbol in INDEX_NAMES and rule.kind != "index":
        raise ValueError("指数代码不能使用股票或 ETF 的交易规则")
    if rule.status != "normal" and not rule.history and not rule.source.strip():
        raise ValueError("非标准证券状态须注明资料来源")
    if rule.tick <= 0 or rule.buy_min <= 0 or rule.buy_step <= 0 or rule.max_order < rule.buy_min:
        raise ValueError("价格步长或申报数量规则无效")
    if rule.t_plus not in (0, 1) or rule.kind == "stock" and rule.t_plus != 1:
        raise ValueError("普通 A 股须按 T+1 处理；ETF 仅支持 T+0/T+1")
    if not 0 <= dec(rule.limit_rate) < 1:
        raise ValueError("涨跌幅比例须在 0 至 1 之间")
    _rule_date(rule.effective_from)
    if not isinstance(rule.known_from, dict):
        raise ValueError("规则启用时刻须按日期保存")
    for day, observed in rule.known_from.items():
        _rule_date(day)
        if (not isinstance(observed, datetime) or observed.tzinfo is None
                or observed.astimezone(CN).date().isoformat() != day):
            raise ValueError("规则启用时刻须含时区，并属于对应中国交易日期")
    previous = ""
    for period in rule.history:
        if not isinstance(period, RulePeriod):
            raise ValueError("历史规则必须使用 RulePeriod 日期区间")
        _rule_date(period.start)
        _rule_date(period.end)
        if period.start > period.end or period.start <= previous:
            raise ValueError("规则区间须按日期排序，不能交叠或倒置（起止日均包含）")
        if not isinstance(period.source, str) or not period.source.strip():
            raise ValueError("每个规则区间须注明公告或资料来源")
        if period.status not in STATUSES:
            raise ValueError("不支持的历史证券状态")
        if period.status == "risk_warning" and rule.kind != "stock":
            raise ValueError("风险警示状态仅适用于股票")
        if period.t_plus is not None and (type(period.t_plus) is not int or period.t_plus not in (0, 1)
                                         or rule.kind == "stock" and period.t_plus != 1):
            raise ValueError("T+0 仅适用于已核对的 ETF")
        if period.limit_rate is not None and not 0 < dec(period.limit_rate) < 1:
            raise ValueError("自定义涨跌幅须大于 0 且小于 1；无限制请选相应状态")
        if period.status in {"risk_warning", "no_limit"} and period.limit_rate is not None:
            raise ValueError("风险警示与无涨跌幅限制状态由日期规则计算，不能另填涨跌幅")
        previous = period.end


def _rule_date(value):
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError()
    except (TypeError, ValueError) as error:
        raise ValueError("规则日期须为 YYYY-MM-DD") from error


def rule_at(rule, day, *, observed_at=None):
    """Resolve only the current interval; never expose future state to a strategy."""
    current = replace(rule, history=[], known_from={})
    if not day:
        if rule.history:
            current.status, current.source = "unknown", "尚无行情日期"
        return current
    if day < rule.effective_from:
        current.status, current.source = "unknown", f"规则只覆盖 {rule.effective_from} 及以后"
        return current
    known = rule.known_from.get(day)
    if known is not None and observed_at is not None and observed_at < known:
        current.status, current.source = "unknown", "当时尚未取得可用规则资料"
        return current
    if rule.history:
        period = next((p for p in rule.history if p.start <= day <= p.end), None)
        if period is None:
            current.status, current.source = "unknown", f"{rule.symbol} {day} 缺少证券状态区间"
            return current
        current.status, current.source = period.status, period.source
        if period.limit_rate is not None:
            current.limit_rate = dec(period.limit_rate)
        if period.t_plus is not None:
            current.t_plus = period.t_plus
    if current.status == "risk_warning":
        current.limit_rate = dec("0.05" if current.board == "main" and day < RULE_CHANGE else
                                 "0.10" if current.board == "main" else "0.20")
    elif current.status == "no_limit":
        current.limit_rate = dec(0)
    return current


def continuous_close(day, rule=None):
    if rule and rule.kind == "index":
        # Research observes the completed closing-auction index value too.
        # This does not authorize fills: index orders are always rejected.
        return time(15)
    # SSE funds introduced a closing auction on 2026-07-06.
    if rule and rule.kind == "etf" and rule.symbol.endswith(".SH") and day < RULE_CHANGE:
        return time(15)
    return time(14, 57)


def rules_summary(rules):
    securities = [r for r in rules.values() if r.kind != "index"]
    indices = len(rules) - len(securities)
    supplied = sum(bool(r.history) for r in securities)
    index_note = f"指数研究序列：{indices} 个，仅观察点位和计算信号，不支持直接买卖。" if indices else ""
    if not securities:
        return index_note
    return (index_note + f"证券状态区间：{supplied}/{len(securities)} 个可交易标的已提供。"
            + ("其余使用标准规则，未核对逐日 ST、上市初期及 ETF 属性。" if supplied < len(securities)
               else "回测会检查区间覆盖日期；自动接口资料与手工公告来源均保留，特殊交易日仍需核对。"))


def default_rule(symbol: str, name: str = "") -> InstrumentRule:
    symbol = symbol_code(symbol)
    code, exchange = symbol.split(".")
    if symbol in INDEX_NAMES:
        # An index is a point series, not shares of an investable security.
        # Broker rejects all orders; these fields only let research bars be read.
        return InstrumentRule(symbol=symbol, name=name or INDEX_NAMES[symbol], kind="index", board="index",
                              tick=dec("0.0001"), buy_min=1, buy_step=1, max_order=1,
                              t_plus=0, limit_rate=dec(0), version="index-research-v1",
                              source="指数点位研究序列，不可直接交易")
    name = name or NAMES.get(symbol, symbol)
    r = InstrumentRule(symbol=symbol, name=name)
    if (exchange == "SH" and code.startswith(("51", "52", "53", "55", "56", "58"))) or (
        exchange == "SZ" and code.startswith(("158", "159"))
    ):
        r.kind, r.board, r.tick = "etf", "etf", dec("0.001")
        r.t_plus = 0 if symbol in T0_ETFS else 1
        if code.startswith("588") or symbol == "159915.SZ":
            r.limit_rate = dec("0.20")
    elif exchange == "SH" and code.startswith("688"):
        r.board, r.buy_min, r.buy_step, r.max_order = "star", 200, 1, 100000
        r.limit_rate = dec("0.20")
    elif exchange == "SZ" and code.startswith(("300", "301")):
        r.board, r.max_order, r.limit_rate = "chinext", 300000, dec("0.20")
    elif (exchange == "SH" and code.startswith(("600", "601", "603", "605"))) or (
        exchange == "SZ" and code.startswith(("000", "001", "002", "003"))
    ):
        pass
    else:
        raise ValueError(f"首版不支持该证券类型：{symbol}")
    return r


def continuous_session(dt: datetime, rule: InstrumentRule | None = None, *, teaching=False) -> bool:
    dt = dt.astimezone(CN)
    if trading_day(dt.date(), teaching=teaching) is not True:
        return False
    t = dt.time().replace(tzinfo=None)
    end = continuous_close(dt.date().isoformat(), rule)
    return time(9, 30) <= t < time(11, 30) or time(13) <= t < end


def minute_bar_start(bar):
    if bar.period not in {"1m", "5m", "15m", "30m", "60m"}:
        return None
    return bar.time - timedelta(minutes=int(bar.period[:-1]))


def continuous_bar(bar, rule, *, teaching=False):
    """A completed bar covers [start, end); its end can be 11:30/14:57/15:00."""
    start = minute_bar_start(bar)
    if start is None or bar.time.tzinfo is None:
        return False
    start, end = start.astimezone(CN), bar.time.astimezone(CN)
    if (start.date() != end.date() or trading_day(end.date(), teaching=teaching) is not True
            or end.second or end.microsecond):
        return False
    close = continuous_close(end.date().isoformat(), rule)
    for opening, closing in ((time(9, 30), time(11, 30)), (time(13), close)):
        session_start = datetime.combine(end.date(), opening, CN)
        session_end = datetime.combine(end.date(), closing, CN)
        if session_start <= start < end <= session_end:
            return (start - session_start).total_seconds() % (int(bar.period[:-1]) * 60) == 0
    return False


def round_tick(price, tick):
    return (dec(price) / tick).quantize(dec(1), rounding=ROUND_HALF_UP) * tick


def tax_rates(day: str, rule: InstrumentRule):
    if rule.kind != "stock":
        return dec(0), dec(0)
    # 印花税卖出收取；过户费双边。佣金由独立模型计算。
    stamp = dec("0.0005") if day >= "2023-08-28" else dec("0.001")
    transfer = dec("0.00001") if day >= "2022-04-29" else dec("0.00002")
    return stamp, transfer
