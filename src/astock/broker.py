"""Deterministic conservative paper broker. The engine is its only writer."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from astock.domain import (
    Account, Bar, CN, CorporateAction, EquityEntry, InstrumentRule, Lot, MatchConfig, Order, Position,
    Quote, Trade, ZERO, dec, money,
)
from astock.accounting import LEGACY_NOTICE, reconcile
from astock.rules import (STATUSES, continuous_bar, continuous_session, minute_bar_start, round_tick,
                          rule_at, tax_rates, validate_rule)
from astock.trading_calendar import trading_day


class Broker:
    def __init__(self, rules: dict[str, InstrumentRule], initial=100000, config=None, *, teaching_calendar=False):
        initial = money(initial)
        if initial <= 0:
            raise ValueError("初始资金必须大于 0")
        for symbol, rule in rules.items():
            validate_rule(rule)
            if symbol != rule.symbol:
                raise ValueError("证券规则与代码不一致")
        self.rules = deepcopy(rules)
        self.teaching_calendar = teaching_calendar
        self.config = config or MatchConfig()
        self.config.validate()
        self.account = Account(initial, initial)
        self.orders: list[Order] = []
        self.trades: list[Trade] = []
        self.sequence = 0
        self.clock: datetime | None = None
        self.market: dict[str, Quote | Bar] = {}
        self.last_times: dict[str, datetime] = {}
        self.day = ""
        self.applied_actions: set[str] = set()
        self.action_definitions: dict[str, CorporateAction] = {}
        self.equity_entries: list[EquityEntry] = []
        self.equity_events: list[EquityEntry] = []
        self.legacy_equity_unverified = False
        self.messages: list[str] = []
        self.order_events: list[Order] = []

    def rule(self, symbol, day=None):
        return rule_at(self.rules[symbol], self.day if day is None else day, observed_at=self.clock)

    def context_rules(self):
        return {symbol: self.rule(symbol) for symbol in self.rules}

    def drain_order_events(self):
        events, self.order_events = self.order_events, []
        return events

    def drain_equity_events(self):
        events, self.equity_events = self.equity_events, []
        return events

    def _post_equity(self, **values):
        entry = EquityEntry(id=f"E{len(self.equity_entries) + 1:06d}", **values)
        self.equity_entries.append(entry)
        self.equity_events.append(entry)

    def _require_verified_ledger(self):
        if self.legacy_equity_unverified:
            raise RuntimeError(LEGACY_NOTICE)

    def _record_order(self, order):
        # A partial fill and cancellation may occur within one bar. Preserve both.
        self.order_events.append(deepcopy(order))

    def _note(self, order, note):
        if order.note != note:
            order.note = note
            self._record_order(order)

    def _wait(self, symbol, note):
        for order in self.orders:
            if order.active and order.symbol == symbol:
                self._note(order, note)

    def remaining_commission(self, order: Order):
        total = order.notional + order.remaining * order.price
        return max(ZERO, max(self.config.minimum_commission, money(total * self.config.commission_rate))
                   - order.commission)

    @property
    def frozen_cash(self):
        value = ZERO
        for order in self.orders:
            if order.active and order.side == "BUY":
                _, transfer = tax_rates(self.day, self.rules[order.symbol])
                value += order.remaining * order.price + self.remaining_commission(order)
                value += max(ZERO, money((order.notional + order.remaining * order.price) * transfer)
                             - order.transfer_fee)
        return value

    @property
    def available_cash(self):
        return self.account.cash - self.frozen_cash

    def available_quantity(self, symbol):
        pos = self.account.positions.get(symbol)
        if not pos:
            return 0
        reserved = sum(o.remaining for o in self.orders if o.active and o.symbol == symbol and o.side == "SELL")
        return pos.sellable(self.day, self.rule(symbol).t_plus) - reserved

    def submit(self, symbol, side, quantity, price, reason="") -> Order:
        self._require_verified_ledger()
        if self.clock is None:
            raise ValueError("尚无有效行情，不能下单")
        price = dec(price)
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise ValueError("委托数量必须为整数")
        order = Order(f"O{len(self.orders) + 1:06d}", symbol, side, quantity, price,
                      self.clock, self.sequence, str(reason)[:2000])
        event = self.market.get(symbol)
        order.next_open = isinstance(event, Bar) and event.period == "1d"
        error = self._validate(order)
        if error:
            order.status, order.note = "REJECTED", error
        elif order.next_open:
            order.note = "等待下一日开盘；届时按成交日涨跌停价格检查"
        self.orders.append(order)
        self._record_order(order)
        return order

    def _validate(self, o):
        r = self.rule(o.symbol) if o.symbol in self.rules else None
        if r is not None and r.kind == "index":
            return "指数仅用于观察和研究，不能直接买卖；请选择对应股票或 ETF。"
        event = self.market.get(o.symbol)
        if r is None or event is None:
            return "该证券未订阅或尚无行情"
        if self.day < r.effective_from:
            return f"规则版本只覆盖 {r.effective_from} 及以后"
        if r.status in {"unknown", "suspended", "unlisted"}:
            return f"{STATUSES[r.status]}：{r.source}"
        if o.side not in ("BUY", "SELL"):
            return "方向必须是 BUY 或 SELL"
        if o.quantity <= 0 or o.quantity > r.max_order:
            return f"委托数量须在 1 至 {r.max_order} 之间"
        if o.price <= 0 or o.price % r.tick:
            return f"价格必须大于 0，且是最小价格单位 {r.tick} 的整数倍"
        if event.suspended:
            return "标的停牌或报价不可用"
        if isinstance(event, Quote):
            if not continuous_session(self.clock, r, teaching=self.teaching_calendar):
                return "当前不在连续竞价时段"
            age = (self.clock - event.time).total_seconds()
            if age > self.config.stale_seconds or age < -2:
                return "行情已过期或时间异常，等待有效行情"
            if (event.upper <= 0 or event.lower <= 0) and r.status != "no_limit":
                return "缺少涨跌停价格；无涨跌幅限制阶段须先提供有来源的证券状态区间"
            if r.kind == "stock":
                base = (event.ask or event.bid or event.last) if o.side == "BUY" else (
                    event.bid or event.ask or event.last
                )
                ceiling = round_tick(max(base * dec("1.02"), base + 10 * r.tick), r.tick)
                floor = round_tick(min(base * dec("0.98"), base - 10 * r.tick), r.tick)
                if o.side == "BUY" and o.price > ceiling or o.side == "SELL" and o.price < floor:
                    return "超出连续竞价有效申报价格范围（价格笼子）"
        upper, lower = self._limits(event, r)
        if not o.next_open and (upper and o.price > upper or lower and o.price < lower):
            return f"委托价超出当日价格范围 {lower}–{upper}"
        if o.side == "BUY":
            if r.status == "risk_warning" and not o.next_open:
                bought = sum(t.quantity for t in self.trades if t.symbol == o.symbol and t.side == "BUY"
                             and t.time.astimezone(CN).date().isoformat() == self.day)
                pending = sum(x.remaining for x in self.orders if x.active and x.symbol == o.symbol and x.side == "BUY")
                if bought + pending + o.quantity > 500000:
                    return "风险警示股票当日累计买入及未撤买单不得超过 50 万股"
            if o.quantity < r.buy_min or (o.quantity - r.buy_min) % r.buy_step:
                return f"最少买入 {r.buy_min}，递增单位 {r.buy_step} 股/份"
            notional = o.quantity * o.price
            _, transfer = tax_rates(self.day, r)
            required = notional + max(self.config.minimum_commission, money(notional * self.config.commission_rate))
            required += money(notional * transfer)
            if required > self.available_cash:
                return "可用资金不足（已计入冻结资金与费用）"
            if notional > self.config.max_order_value:
                return "超过单笔金额上限"
            pos = self.account.positions.get(o.symbol)
            held = pos.quantity * pos.last if pos else ZERO
            pending = sum(x.remaining * x.price for x in self.orders
                          if x.active and x.side == "BUY" and x.symbol == o.symbol)
            if held + pending + notional > self.account.equity * self.config.max_position_ratio:
                return "超过单标的仓位上限"
        else:
            available = self.available_quantity(o.symbol)
            if o.quantity > available:
                return "可卖数量不足：检查 T+1 持仓或已有卖出委托"
            if r.board == "star":
                if o.quantity < r.buy_min and o.quantity != available:
                    return "不足 200 股的余股必须一次性卖出"
            elif o.quantity % 100 and o.quantity != available:
                return "零股余额必须一次性卖出"
        return ""

    @staticmethod
    def _limits(event, rule):
        if rule.status == "no_limit":
            return ZERO, ZERO
        upper, lower = event.upper, event.lower
        if not upper and event.prev_close > 0 and rule.limit_rate > 0:
            upper = round_tick(event.prev_close * (1 + rule.limit_rate), rule.tick)
            lower = round_tick(event.prev_close * (1 - rule.limit_rate), rule.tick)
        return upper, lower

    def cancel(self, order_id, note="已撤单，释放冻结资金/持仓"):
        for order in self.orders:
            if order.id == order_id and order.active:
                order.status, order.note = "CANCELED", note
                self._record_order(order)
                return

    def cancel_all(self, note="停止策略，撤销剩余委托"):
        for o in self.orders:
            if o.active:
                self.cancel(o.id, note)

    def _roll_day(self, day):
        if self.day and day > self.day:
            for o in self.orders:
                if o.active and not o.next_open:
                    self.cancel(o.id, "当日委托已到期")
        self.day = day
        pending = []
        settled = False
        for item in self.account.receivables:
            if item["pay_date"] <= day:
                amount = dec(item["amount"])
                action = self.action_definitions[item["action_key"]]
                self.account.cash += amount
                self._post_equity(action_key=item["action_key"], symbol=item["symbol"], kind="payment",
                                  time=self.clock, cash_delta=amount, receivable_delta=-amount,
                                  pay_date=item["pay_date"], share_available_date=action.share_available_date)
                settled = True
            else:
                pending.append(item)
        self.account.receivables = pending
        if settled:
            self.check_invariants()

    def on_event(self, event: Quote | Bar, live_now: datetime | None = None):
        self._require_verified_ledger()
        if event.symbol not in self.rules:
            return []
        if event.time.tzinfo is None:
            raise ValueError("行情必须包含时区")
        day = event.time.astimezone(CN).date().isoformat()
        r = self.rule(event.symbol, day)
        day_status = trading_day(event.time.astimezone(CN).date(), teaching=self.teaching_calendar)
        if day_status is not True:
            self._wait(event.symbol, "交易所休市，暂停撮合" if day_status is False else "交易日历尚未覆盖该日期，暂停撮合")
            return []
        if live_now is not None:
            if live_now.tzinfo is None:
                raise ValueError("观察时间必须包含时区")
            if self.clock and live_now < self.clock:
                return []
        last_time = self.last_times.get(event.symbol)
        if last_time and event.time <= last_time:
            return []
        # 多标的同时间可接受；全局时钟不得倒退。
        if self.clock and event.time < self.clock and live_now is None:
            return []
        prior = self.market.get(event.symbol)
        if self.day and day < self.day:
            return []
        self.sequence += 1
        self.clock = live_now or event.time
        self._roll_day(day)
        self.last_times[event.symbol] = event.time
        self.market[event.symbol] = event
        last = event.last if isinstance(event, Quote) else event.close
        if last <= 0:
            self._wait(event.symbol, "缺少有效价格，暂停撮合")
            self._expire_daily(event)
            return []
        if event.symbol in self.account.positions:
            self.account.positions[event.symbol].last = last
        if r.status in {"unknown", "suspended", "unlisted"}:
            self._wait(event.symbol, f"{STATUSES[r.status]}：{r.source}，暂停撮合")
            self._expire_daily(event)
            return []
        if event.suspended:
            self._wait(event.symbol, "标的停牌，暂停撮合")
            self._expire_daily(event)
            return []
        if isinstance(event, Quote):
            if (not continuous_session(event.time, r, teaching=self.teaching_calendar)
                    or not continuous_session(self.clock, r, teaching=self.teaching_calendar)):
                self._wait(event.symbol, "非连续竞价时段，暂停撮合")
                return []
            if r.status != "no_limit" and (event.upper <= 0 or event.lower <= 0):
                self._wait(event.symbol, "缺少当日涨跌停价格，暂停撮合")
                return []
            if live_now is not None:
                age = (live_now - event.time).total_seconds()
                if not -2 <= age <= self.config.stale_seconds:
                    self._wait(event.symbol, "行情已过期或时间异常，暂停撮合")
                    return []
            # 首次/跨日/断流后的快照只建立基线；不将缺口累计量当作当前可成交量。
            if (not isinstance(prior, Quote)
                    or prior.time.astimezone(CN).date() != event.time.astimezone(CN).date()):
                self._wait(event.symbol, "首条有效快照建立成交量基线，等待下一条行情")
                return []
            if (event.time - prior.time).total_seconds() > self.config.stale_seconds:
                self._wait(event.symbol, "行情存在断流，重新建立成交量基线")
                return []
            delta = event.volume - prior.volume
            if delta <= 0:
                self._wait(event.symbol, "累计成交量未增加，暂无可分配流动性")
                return []
            total_budget = int(dec(delta) * self.config.participation)
            side_budget = {
                "BUY": min(total_budget, int(dec(event.ask_size) * self.config.participation)),
                "SELL": min(total_budget, int(dec(event.bid_size) * self.config.participation)),
            }
        else:
            if event.period != "1d" and not continuous_bar(event, r, teaching=self.teaching_calendar):
                self._wait(event.symbol, "该 K 线覆盖休市/集合竞价或时间边界不明，暂停撮合")
                return []
            if event.volume <= 0 or event.low <= 0 or not event.low <= event.open <= event.high:
                self._wait(event.symbol, "K 线缺少有效开盘价或成交量，暂停撮合")
                self._expire_daily(event)
                return []
            total_budget = int(dec(event.volume) * self.config.participation)
            side_budget = {"BUY": total_budget, "SELL": total_budget}
        result = []
        upper, lower = self._limits(event, r)
        for order in self.orders:
            if not order.active or order.symbol != event.symbol:
                continue
            if order.sequence >= self.sequence or order.created >= event.time:
                continue
            if isinstance(event, Bar) and event.period != "1d" and order.created > minute_bar_start(event):
                self._note(order, "委托晚于该 K 线开盘，等待下一根完整 K 线")
                continue
            if upper and order.price > upper or lower and order.price < lower:
                if order.next_open:
                    order.status, order.note = "REJECTED", f"下一日开盘委托价超出成交日价格范围 {lower}–{upper}"
                    self._record_order(order)
                else:
                    self._note(order, "当前委托价超出价格范围")
                continue
            price = self._match_price(order, event, r, upper, lower)
            if price is None:
                self._note(order, "价格未触及、缺少对手报价或封板；继续等待")
                continue
            quantity = min(order.remaining, total_budget, side_budget[order.side])
            if r.status == "risk_warning" and order.side == "BUY":
                bought = sum(t.quantity for t in self.trades if t.symbol == event.symbol and t.side == "BUY"
                             and t.time.astimezone(CN).date().isoformat() == self.day)
                quantity = min(quantity, max(0, 500000 - bought))
                if not quantity:
                    self._note(order, "风险警示股票当日累计买入已达 50 万股，停止新增成交")
                    continue
            # 部分成交数量可以小于申报单位，但不能凭空创造流动性。
            if quantity <= 0:
                self._note(order, "可见流动性不足，等待后续行情")
                continue
            trade = self._fill(order, quantity, price, event.time)
            total_budget -= quantity
            side_budget[order.side] -= quantity
            result.append(trade)
        self.check_invariants()
        self._expire_daily(event)
        return result

    def _expire_daily(self, event):
        if isinstance(event, Bar) and event.period == "1d":
            for o in self.orders:
                if o.active and o.symbol == event.symbol and o.created < event.time:
                    self.cancel(o.id, "下一日开盘撮合结束或不可交易，撤销未成交余量")

    def _match_price(self, order, event, rule, upper, lower):
        slip = self.config.slippage_ticks * rule.tick
        if isinstance(event, Quote):
            if order.side == "BUY":
                if event.ask <= 0 or event.ask_size <= 0:
                    return None
                price = event.ask + slip
                if price > order.price or upper and price > upper:
                    return None
            else:
                if event.bid <= 0 or event.bid_size <= 0:
                    return None
                price = event.bid - slip
                if price < order.price or lower and price < lower:
                    return None
            return price if price > 0 else None
        # 不假设一字板可成交；只使用下一根已完成 K 线的开盘价，避免推断柱内路径。
        if event.high == event.low and (upper and event.high >= upper or lower and event.low <= lower):
            return None
        if order.side == "BUY":
            price = event.open + slip
            if price > order.price or price > event.high or upper and price > upper:
                return None
        else:
            price = event.open - slip
            if price < order.price or price < event.low or lower and price < lower:
                return None
        return price if price > 0 else None

    def _fill(self, order, quantity, price, dt):
        notional = quantity * price
        total_commission = max(self.config.minimum_commission,
                               money((order.notional + notional) * self.config.commission_rate))
        commission = total_commission - order.commission
        stamp, transfer = tax_rates(dt.astimezone(CN).date().isoformat(), self.rule(order.symbol))
        transfer_total = money((order.notional + notional) * transfer)
        stamp_total = money((order.notional + notional) * stamp) if order.side == "SELL" else ZERO
        fee = commission + transfer_total - order.transfer_fee + stamp_total - order.stamp_fee
        pos = self.account.positions.setdefault(order.symbol, Position(order.symbol))
        pos.last = self.market[order.symbol].last if isinstance(self.market[order.symbol], Quote) else (
            self.market[order.symbol].close
        )
        realized = ZERO
        if order.side == "BUY":
            self.account.cash -= notional + fee
            pos.cost += notional + fee
            pos.lots.append(Lot(quantity, dt.astimezone(CN).date().isoformat()))
        else:
            cost = pos.cost * dec(quantity) / dec(pos.quantity)
            pos.cost -= cost
            left = quantity
            for lot in pos.lots:
                if not lot.available(self.day, self.rule(order.symbol).t_plus):
                    continue
                used = min(lot.quantity, left)
                lot.quantity -= used
                left -= used
            pos.lots = [x for x in pos.lots if x.quantity]
            if left:
                raise RuntimeError("成交超过可卖持仓")
            self.account.cash += notional - fee
            realized = notional - fee - cost
            self.account.realized += realized
        self.account.fees += fee
        order.filled += quantity
        order.notional += notional
        order.commission = total_commission
        order.transfer_fee = transfer_total
        order.stamp_fee = stamp_total
        order.fees += fee
        order.status = "FILLED" if not order.remaining else "PARTIAL"
        order.note = "全部成交" if not order.remaining else f"部分成交，剩余 {order.remaining} 股/份"
        trade = Trade(f"T{len(self.trades) + 1:06d}", order.id, order.symbol, order.side,
                      quantity, price, fee, dt, order.reason, realized)
        self.trades.append(trade)
        self._record_order(order)
        return trade

    def corporate_action(self, action: CorporateAction):
        self._require_verified_ledger()
        action.validate()
        if trading_day(action.time.astimezone(CN).date(), teaching=self.teaching_calendar) is not True:
            raise ValueError("权益事件日期不是已核对的交易日，不能入账")
        key = action.key
        if key in self.applied_actions:
            if action != self.action_definitions[key]:
                raise ValueError("同一权益事件编号的内容发生变化，不能重复或覆盖入账")
            return
        if action.symbol not in self.rules:
            raise ValueError("权益事件证券未包含在账户规则中")
        if self.clock and action.time < self.clock:
            raise ValueError("权益事件必须按时间顺序处理")
        self.check_invariants()
        pos = self.account.positions.get(action.symbol)
        quantity = pos.quantity if pos else 0
        new_quantity = dec(quantity) * action.share_multiplier
        if new_quantity != new_quantity.to_integral_value():
            raise ValueError("权益事件产生零碎份额，需提供准确到账数据")
        day = action.time.astimezone(CN).date().isoformat()
        if pos and quantity:
            if action.cash_per_share >= pos.last:
                raise ValueError("现金分红不小于除权前估值，需提供准确价格与权益资料")
            if any(lot.acquired >= day or lot.available_from > day for lot in pos.lots):
                raise ValueError("权益登记持仓包含当日买入或尚未上市的份额，需补充准确权益资料")
        dividend = money(quantity * action.cash_per_share)
        delta = int(new_quantity) - quantity
        self.clock = action.time
        self._roll_day(day)
        for order in self.orders:
            if order.symbol == action.symbol and order.active:
                self.cancel(order.id, "权益变动：撤销该证券旧价格委托")
        self.action_definitions[key] = deepcopy(action)
        self.applied_actions.add(key)
        self._post_equity(action_key=key, symbol=action.symbol, kind="entitlement", time=action.time,
                          quantity_before=quantity, quantity_delta=delta, receivable_delta=dividend,
                          pay_date=action.pay_date, share_available_date=action.share_available_date)
        if pos and quantity:
            if dividend:
                self.account.receivables.append({"action_key": key, "symbol": action.symbol,
                                                 "amount": dividend, "pay_date": action.pay_date})
            if delta > 0:
                # 所有登记份额均在此前取得；新增份额使用独立的上市日期约束。
                pos.lots.append(Lot(delta, max(lot.acquired for lot in pos.lots), action.share_available_date))
            elif delta < 0:
                pos.lots = [Lot(int(new_quantity), max(lot.acquired for lot in pos.lots),
                                action.share_available_date)]
            pos.last = (pos.last - action.cash_per_share) / action.share_multiplier
        # 不能在除权后继续拿昨日价格下单；等该标的的新行情。
        self.market.pop(action.symbol, None)
        self._roll_day(self.day)
        self.check_invariants()

    def check_invariants(self):
        if self.account.cash < 0 or self.available_cash < dec("-0.02"):
            raise RuntimeError("记账校验失败：资金为负")
        for symbol, pos in self.account.positions.items():
            if (pos.quantity < 0 or self.available_quantity(symbol) < 0
                    or any(lot.quantity <= 0 for lot in pos.lots)):
                raise RuntimeError("记账校验失败：持仓为负")
        reconcile(self)

    def snapshot(self):
        return {"account": self.account, "orders": self.orders, "trades": self.trades,
                "sequence": self.sequence, "day": self.day, "clock": self.clock,
                "applied_actions": sorted(self.applied_actions), "config": self.config, "rules": self.rules,
                "equity_ledger_version": 1, "equity_entries": self.equity_entries,
                "action_definitions": self.action_definitions,
                "teaching_calendar": self.teaching_calendar,
                "legacy_equity_unverified": self.legacy_equity_unverified}

    @classmethod
    def restore(cls, snapshot):
        if snapshot.get("equity_ledger_version", 1) != 1:
            raise ValueError("不支持该权益流水版本，不能按旧格式恢复")
        obj = cls(snapshot["rules"], snapshot["account"].initial, snapshot["config"],
                  teaching_calendar=snapshot.get("teaching_calendar", False))
        for key in ("account", "orders", "trades", "sequence", "day", "clock"):
            setattr(obj, key, snapshot[key])
        obj.applied_actions = set(snapshot.get("applied_actions", []))
        obj.equity_entries = snapshot.get("equity_entries", [])
        obj.action_definitions = snapshot.get("action_definitions", {})
        obj.legacy_equity_unverified = snapshot.get("legacy_equity_unverified", False) or (
            "equity_ledger_version" not in snapshot and bool(obj.applied_actions or obj.account.receivables))
        obj.cancel_all("重启恢复：取消旧委托，策略保持暂停")
        if not obj.legacy_equity_unverified:
            obj.check_invariants()
        return obj
