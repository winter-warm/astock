from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol
import json
import re

CN = timezone(timedelta(hours=8))
ZERO = Decimal("0")


def dec(value=0) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("数值必须是有限数")
    return result


def money(value) -> Decimal:
    return dec(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def now_cn() -> datetime:
    return datetime.now(CN)


def symbol_code(value: str) -> str:
    value = value.strip().upper()
    if re.fullmatch(r"(SH|SZ)\d{6}", value):
        value = value[2:] + "." + value[:2]
    if re.fullmatch(r"\d{6}", value):
        value += ".SH" if value.startswith(("5", "6")) else ".SZ"
    if not re.fullmatch(r"\d{6}\.(SH|SZ)", value):
        raise ValueError(f"不支持的证券代码：{value}；例如 600000.SH、159915.SZ")
    return value


@dataclass
class Quote:
    symbol: str
    time: datetime
    received: datetime
    last: Decimal
    bid: Decimal = ZERO
    ask: Decimal = ZERO
    bid_size: int = 0
    ask_size: int = 0
    volume: int = 0  # 累计股数/份数，适配层统一单位
    prev_close: Decimal = ZERO
    upper: Decimal = ZERO
    lower: Decimal = ZERO
    name: str = ""
    source: str = "tencent"
    suspended: bool = False
    # The engine's actual observation time, distinct from provider and collector
    # clocks. Recorded live inputs retain queue delay when replayed.
    observed: datetime | None = None


def event_clock(event):
    if isinstance(event, Quote):
        return event.observed or event.received
    return event.time


@dataclass
class Bar:
    symbol: str
    time: datetime  # 已完成 K 线的结束时刻
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int  # 当前 K 线股数/份数
    period: str = "1d"
    prev_close: Decimal = ZERO
    factor: Decimal = Decimal("1")
    upper: Decimal = ZERO
    lower: Decimal = ZERO
    suspended: bool = False


@dataclass
class CorporateAction:
    symbol: str
    time: datetime
    cash_per_share: Decimal = ZERO
    share_multiplier: Decimal = Decimal("1")
    action_id: str = ""
    # 现金红利以应收权益计入总资产，到账日转为可用现金。
    pay_date: str = ""
    # 新增份额上市/可卖日期须来自权益资料，不能从除权日推断。
    share_available_date: str = ""

    @property
    def key(self):
        return f"{self.symbol}:{self.action_id or self.time.isoformat()}"

    def validate(self):
        if self.time.tzinfo is None:
            raise ValueError("权益事件必须包含时区")
        local = self.time.astimezone(CN)
        if local.weekday() >= 5 or local.time().replace(tzinfo=None) >= time(9, 30):
            raise ValueError("权益事件须在除权日开盘前处理，不能用盘中持仓推断登记权益")
        if dec(self.cash_per_share) < 0 or dec(self.share_multiplier) <= 0:
            raise ValueError("权益事件数值无效")
        for value, required, name in ((self.pay_date, self.cash_per_share > 0, "现金分红到账日期"),
                                      (self.share_available_date, self.share_multiplier != 1, "份额可卖日期")):
            if required and not value:
                raise ValueError(f"权益事件缺少{name}")
            if value:
                try:
                    parsed = date.fromisoformat(value)
                except (TypeError, ValueError) as error:
                    raise ValueError(f"{name}须为 YYYY-MM-DD") from error
                if parsed.isoformat() != value or parsed < local.date():
                    raise ValueError(f"{name}格式无效或早于权益事件日期")


@dataclass(frozen=True)
class EquityEntry:
    id: str
    action_key: str
    symbol: str
    kind: str  # entitlement / payment
    time: datetime  # 入账观察时刻，pay_date 保留约定到账日
    quantity_before: int = 0
    quantity_delta: int = 0
    cash_delta: Decimal = ZERO
    receivable_delta: Decimal = ZERO
    pay_date: str = ""
    share_available_date: str = ""


@dataclass(frozen=True)
class RulePeriod:
    start: str
    end: str
    source: str
    status: str = "normal"
    limit_rate: Decimal | None = None
    t_plus: int | None = None


@dataclass
class InstrumentRule:
    symbol: str
    name: str = ""
    kind: str = "stock"  # stock / etf are tradable; index is a research-only point series.
    board: str = "main"
    tick: Decimal = Decimal("0.01")
    buy_min: int = 100
    buy_step: int = 100
    max_order: int = 1000000
    t_plus: int = 1
    limit_rate: Decimal = Decimal("0.10")
    effective_from: str = "2023-04-10"
    version: str = "cn-continuous-2026.11-v2"
    history: list[RulePeriod] = field(default_factory=list)
    known_from: dict[str, datetime] = field(default_factory=dict)
    status: str = "normal"
    source: str = ""


@dataclass
class Lot:
    quantity: int
    acquired: str
    available_from: str = ""

    def available(self, day, t_plus):
        return (not self.available_from or self.available_from <= day) and (not t_plus or self.acquired < day)


@dataclass
class Position:
    symbol: str
    lots: list[Lot] = field(default_factory=list)
    cost: Decimal = ZERO
    last: Decimal = ZERO

    @property
    def quantity(self):
        return sum(x.quantity for x in self.lots)

    def sellable(self, day: str, t_plus: int):
        return sum(x.quantity for x in self.lots if x.available(day, t_plus))


@dataclass
class Order:
    id: str
    symbol: str
    side: str
    quantity: int
    price: Decimal
    created: datetime
    sequence: int
    reason: str = ""
    status: str = "OPEN"
    filled: int = 0
    notional: Decimal = ZERO
    commission: Decimal = ZERO
    transfer_fee: Decimal = ZERO
    stamp_fee: Decimal = ZERO
    fees: Decimal = ZERO
    note: str = "等待下一条有效行情"
    next_open: bool = False  # 日线收盘信号对应下一交易日开盘的模拟委托

    @property
    def remaining(self):
        return self.quantity - self.filled

    @property
    def active(self):
        return self.status in ("OPEN", "PARTIAL")


@dataclass
class Trade:
    id: str
    order_id: str
    symbol: str
    side: str
    quantity: int
    price: Decimal
    fee: Decimal
    time: datetime
    reason: str
    realized: Decimal = ZERO


@dataclass
class Account:
    initial: Decimal = Decimal("100000")
    cash: Decimal = Decimal("100000")
    positions: dict[str, Position] = field(default_factory=dict)
    fees: Decimal = ZERO
    realized: Decimal = ZERO
    receivables: list[dict] = field(default_factory=list)

    @property
    def equity(self):
        return self.cash + sum((p.quantity * p.last for p in self.positions.values()), ZERO) + sum(
            (dec(x["amount"]) for x in self.receivables), ZERO
        )


@dataclass
class MatchConfig:
    commission_rate: Decimal = Decimal("0.0003")
    minimum_commission: Decimal = Decimal("5")
    participation: Decimal = Decimal("0.10")
    slippage_ticks: int = 1
    stale_seconds: int = 15
    max_position_ratio: Decimal = Decimal("1")
    max_order_value: Decimal = Decimal("100000")
    version: str = "conservative-v2"

    def validate(self):
        if not ZERO < self.participation <= 1:
            raise ValueError("成交参与率必须大于 0 且不超过 1")
        if min(self.commission_rate, self.minimum_commission, dec(self.slippage_ticks)) < 0:
            raise ValueError("手续费和滑点不能为负数")
        if not ZERO < self.max_position_ratio <= 1 or self.max_order_value <= 0:
            raise ValueError("仓位及单笔额度配置无效")
        if self.stale_seconds < 1:
            raise ValueError("过期阈值必须大于 0")


class MarketProvider(Protocol):
    def quotes(self, symbols: list[str]) -> list[Quote]: ...


class SimulatedBroker(Protocol):
    def submit(self, symbol: str, side: str, quantity: int, price, reason: str = "") -> Order: ...
    def cancel(self, order_id: str) -> None: ...
    def drain_order_events(self) -> list[Order]: ...


TYPES = {c.__name__: c for c in (
    Quote, Bar, CorporateAction, EquityEntry, RulePeriod, InstrumentRule, Lot, Position, Order, Trade, Account, MatchConfig
)}


def encode(value):
    if hasattr(value, "__dataclass_fields__"):
        return {"__type__": type(value).__name__, **{k: encode(v) for k, v in vars(value).items()}}
    if isinstance(value, Decimal):
        return {"__decimal__": str(value)}
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    return value


def decode(value):
    if isinstance(value, list):
        return [decode(x) for x in value]
    if isinstance(value, dict):
        if "__decimal__" in value:
            return dec(value["__decimal__"])
        if "__datetime__" in value:
            return datetime.fromisoformat(value["__datetime__"])
        if "__type__" in value:
            return TYPES[value["__type__"]](**{k: decode(v) for k, v in value.items() if k != "__type__"})
        return {k: decode(v) for k, v in value.items()}
    return value


def dumps(value) -> str:
    return json.dumps(encode(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def loads(value: str):
    return decode(json.loads(value))


def plain(value):
    """JSON friendly display/export data (not used for restoring accounting)."""
    if hasattr(value, "__dataclass_fields__"):
        return plain(asdict(value))
    if isinstance(value, (Decimal, datetime, date)):
        return str(value)
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value
