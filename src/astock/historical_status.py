"""Sourced, dated stock states; current names never determine historical ST."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import socket
from types import SimpleNamespace

from astock.domain import RulePeriod, dumps, now_cn
from astock.rules import validate_rule
from astock.trading_calendar import manifest, trading_day

SOURCE = "https://www.baostock.com/mainContent?file=stockKData.md"
BASIC_SOURCE = "https://www.baostock.com/mainContent?file=stockBasic.md"
IPO_SOURCE = "https://investor.szse.cn/knowledge/stock/deal/t20230525_600599.html"
FIELDS = "date,code,tradestatus,isST"
NOTICE = ("自动资料覆盖股票逐日 ST、整日停牌及上市日期。非 ST 日沿用板块标准涨跌幅；"
          "重新上市等特殊无限制日仍须核对公告。ETF 的 T+0/T+1 不由本接口推断。")


def digest(value):
    return hashlib.sha256(dumps(value).encode("utf-8")).hexdigest()


def checked_date(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("来源日期须为 YYYY-MM-DD")
    return date.fromisoformat(value)


def request_dates(rule, start, end):
    validate_rule(rule)
    if rule.kind != "stock":
        raise ValueError("此接口仅自动整理股票状态；ETF 可卖规则请使用有来源的日期区间。")
    first, last = checked_date(start), checked_date(end)
    if first > last or first < date(2023, 4, 10) or last > now_cn().date():
        raise ValueError("状态请求须为 2023-04-10 起、截至今天的有效日期区间")
    if trading_day(first) is None or trading_day(last) is None:
        raise ValueError("状态请求超出已核对交易日历范围")
    return first, last


def normalize_status(rule, start, end, basic, rows, *, received=None, version=""):
    first, last = request_dates(rule, start, end)
    code = rule.symbol[-2:].lower() + "." + rule.symbol[:6]
    if len(basic) != 1 or basic[0].get("code") != code or basic[0].get("type") != "1":
        raise ValueError("来源未返回该股票唯一的上市资料；不套用其他证券资料")
    info = basic[0]
    ipo = checked_date(info.get("ipoDate", ""))
    out = checked_date(info["outDate"]) if info.get("outDate") else None
    if out and out <= ipo:
        raise ValueError("来源上市与退市日期冲突")
    indexed, previous = {}, None
    for row in rows:
        if row.get("code") != code or set(row) != set(FIELDS.split(",")):
            raise ValueError("逐日状态字段或证券代码与请求不符")
        day = checked_date(row["date"])
        if not first <= day <= last or previous and day <= previous:
            raise ValueError("逐日状态超出请求日期、重复或乱序")
        if trading_day(day) is not True:
            raise ValueError("来源状态日期与交易所日历不一致")
        if day < ipo or out and day >= out:
            raise ValueError("来源逐日记录与上市/退市日期冲突")
        if row["tradestatus"] not in {"0", "1"} or row["isST"] not in {"0", "1"}:
            raise ValueError("逐日 ST 或停牌标记缺失/不合法，不能当作正常交易")
        previous, indexed[day] = day, row

    # Only derive the registered-IPO first five exchange sessions within the
    # supported rule/calendar era. Relisting cannot be inferred from this field.
    ipo_days = set()
    if ipo >= date(2023, 4, 10) and ipo <= last:
        if trading_day(ipo) is not True:
            raise ValueError("上市日期不在已核对的交易日历内")
        current = ipo
        while len(ipo_days) < 5 and current <= last:
            if trading_day(current) is None:
                raise ValueError("新股前五日超出日历范围")
            if trading_day(current):
                ipo_days.add(current)
            current += timedelta(days=1)

    periods, missing, counts = [], [], Counter()
    current = first
    while current <= last:
        if trading_day(current):
            source = SOURCE
            row = indexed.get(current)
            if current < ipo or out and current >= out:
                status, source = "unlisted", BASIC_SOURCE
            elif row is None:
                status = "unknown"
                missing.append(current.isoformat())
            elif row["tradestatus"] == "0":
                status = "suspended"
            elif current in ipo_days:
                if row["isST"] != "0":
                    raise ValueError("来源新股前五日与风险警示标记冲突")
                status, source = "no_limit", BASIC_SOURCE + " ; " + IPO_SOURCE
            else:
                status = "risk_warning" if row["isST"] == "1" else "normal"
            counts[status] += 1
            day = current.isoformat()
            # Iterating every exchange session prevents bridging a missing day.
            if periods and periods[-1].status == status and periods[-1].source == source:
                old = periods[-1]
                periods[-1] = RulePeriod(old.start, day, source, status)
            else:
                periods.append(RulePeriod(day, day, source, status))
        current += timedelta(days=1)
    if not periods:
        raise ValueError("所选范围内没有交易日")
    audit = {"adapter": "stock-status-baostock-v1", "symbol": rule.symbol,
             "source": SOURCE, "basic_source": BASIC_SOURCE, "provider_version": version,
             "received_at": (received or now_cn()).isoformat(), "request": {"start": start, "end": end},
             "calendar": manifest(), "basic": deepcopy(basic), "rows": deepcopy(rows),
             "basic_sha256": digest(basic), "rows_sha256": digest(rows),
             "proposed_periods": list(periods), "missing_dates": missing,
             "counts": dict(counts), "scope": NOTICE}
    return {"symbol": rule.symbol, "periods": periods, "audit": audit}


def read_result(result, max_rows=2500):
    rows = []
    if result.error_code != "0":
        raise RuntimeError(f"历史状态接口：{result.error_code} {result.error_msg}")
    while result.next():
        if result.error_code != "0":
            raise RuntimeError(f"历史状态接口：{result.error_code} {result.error_msg}")
        values = result.get_row_data()
        if len(set(result.fields)) != len(result.fields):
            raise ValueError("来源返回重复字段")
        rows.append(dict(zip(result.fields, values, strict=True)))
        if len(rows) > max_rows:
            raise ValueError("历史状态响应超出支持的记录数")
    if result.error_code != "0":
        raise RuntimeError(f"历史状态接口分页中断：{result.error_code} {result.error_msg}")
    return rows


class StatusSocket(socket.socket):
    def recv(self, *args, **kwargs):
        data = super().recv(*args, **kwargs)
        if not data:
            self.peer_closed = True
            raise ConnectionError("历史资料服务关闭了连接，未返回完整响应")
        return data


def fetch_status(request, progress=lambda _: None):
    rule, start, end = request["rule"], request["start"], request["end"]
    request_dates(rule, start, end)
    import baostock as bs
    import baostock.util.socketutil as transport
    previous_transport = transport.socket
    connections = []
    def make_socket(*args, **kwargs):
        connection = StatusSocket(*args, **kwargs)
        connections.append(connection)
        return connection
    # The pinned SDK otherwise loops forever on recv(b''). Patch only its
    # transport module in this isolated worker, not Python's global socket API.
    transport.socket = SimpleNamespace(socket=make_socket, AF_INET=socket.AF_INET, SOCK_STREAM=socket.SOCK_STREAM)
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(8)
    try:
        progress({"phase": "连接历史状态资料源", "done": 0})
        login = bs.login()
        if login.error_code != "0":
            raise RuntimeError(f"历史状态连接失败：{login.error_code} {login.error_msg}")
        code = rule.symbol[-2:].lower() + "." + rule.symbol[:6]
        progress({"phase": f"获取 {rule.symbol} 上市与逐日状态", "done": 1})
        basic = read_result(bs.query_stock_basic(code=code), 1)
        rows = read_result(bs.query_history_k_data_plus(code, FIELDS, start_date=start, end_date=end,
                                                       frequency="d", adjustflag="3"))
        return normalize_status(rule, start, end, basic, rows, version=bs.__version__)
    except Exception as error:
        if any(getattr(connection, "peer_closed", False) for connection in connections):
            raise RuntimeError("历史状态资料服务已关闭连接，未返回完整响应；请稍后重试。原规则未修改。") from error
        raise
    finally:
        try:
            bs.logout()
        finally:
            for connection in connections:
                connection.close()
            socket.setdefaulttimeout(old_timeout)
            transport.socket = previous_transport
