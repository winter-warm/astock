from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import replace
from datetime import date
import hashlib
from pathlib import Path
from queue import Empty
import time
import traceback
import uuid

from astock.broker import Broker
from astock import __version__
from astock.datasets import load_dataset
from astock.domain import Bar, CN, CorporateAction, MatchConfig, Quote, event_clock, loads, now_cn
from astock.input_archive import InputArchive, finalize_inputs
from astock.rules import RULE_ENGINE_VERSION, rules_summary
from astock.storage import Store
from astock.strategy import StrategyHost
from astock.data_quality import coverage_text
from astock.trading_calendar import manifest as calendar_manifest


def performance(curve, broker):
    equity = float(broker.account.equity)
    initial = float(broker.account.initial)
    max_dd = max((p["drawdown"] for p in curve), default=0)
    sells = [t for t in broker.trades if t.side == "SELL"]
    return {"equity": equity, "return": equity / initial - 1,
            "max_drawdown": max_dd, "fees": float(broker.account.fees),
            "trades": len(broker.trades), "realized": float(broker.account.realized),
            "dividends_paid": float(sum((entry.cash_delta for entry in broker.equity_entries), 0)),
            "dividends_receivable": float(sum((item["amount"] for item in broker.account.receivables), 0)),
            "profitable_sells": sum(t.realized > 0 for t in sells) / len(sells) if sells else None,
            "benchmark_return": curve[-1]["benchmark"] / initial - 1 if curve else 0}


class Run:
    def __init__(self, request, root, output):
        self.id = uuid.uuid4().hex[:12]
        self.name = request.get("name", "策略")
        self.mode = request["mode"]
        self.output = output
        self.status = "PAUSED"
        self.host = None
        self.index = 0
        self.events = []
        self.history = defaultdict(list)
        self.times = {}
        self.prices = defaultdict(list)
        self.curve = []
        self.logs = []
        self.journal = []
        self.reported_order_ids = set()
        self.pending_order_events = deque()
        self.notifying_orders = False
        self.peak = float(request.get("initial", 100000))
        self.benchmark_start = None
        self.next_due = 0.0
        self.speed = float(request.get("speed", 20))
        self.dirty = True
        self.last_emit = 0.0
        self.last_save = 0.0
        self.dataset = None
        self.root = Path(root)
        self.input_archive = None
        live_audit = None
        run_window = None
        if self.mode in ("backtest", "replay"):
            self.dataset, self.events = load_dataset(Path(root) / "datasets", request["dataset"])
            expected = "quote" if self.mode == "replay" else "bar"
            if self.dataset["kind"] != expected:
                raise ValueError("运行模式与数据类型不一致：快照用于回放，K 线用于回测")
            rules = self.dataset["rules"]
            if self.mode == "backtest" and request.get("backtest_window"):
                selected = request["backtest_window"]
                start, end = date.fromisoformat(selected["start"]), date.fromisoformat(selected["end"])
                if start > end:
                    raise ValueError("回测开始日期不能晚于结束日期")
                self.events = [e for e in self.events if start <= event_clock(e).astimezone(CN).date() <= end]
                bars = [e for e in self.events if isinstance(e, Bar)]
                if not bars:
                    raise ValueError("所选回测区间没有 K 线，请调整日期或下载对应数据")
                run_window = {"start": start.isoformat(), "end": end.isoformat(),
                              "actual_start": event_clock(self.events[0]), "actual_end": event_clock(self.events[-1]),
                              "count": len(self.events), "warmup": "仅使用区间内行情，不预读区间外数据"}
        else:
            from astock.live_rules import read_live_rules
            rules, live_audit = read_live_rules(root, request["symbols"], now_cn())
        self.broker = Broker(rules, request.get("initial", 100000), request.get("config", MatchConfig()),
                             teaching_calendar=bool(self.dataset and self.dataset.get("demo")))
        if self.mode in ("live", "manual"):
            self.input_archive = InputArchive(root, self.id)
        self.benchmark_symbol = request.get("benchmark_symbol") or list(rules)[0]
        if self.benchmark_symbol not in rules:
            raise ValueError("基准必须是当前数据中的证券")
        if self.mode == "backtest" and not any(isinstance(e, Bar) and e.symbol == self.benchmark_symbol for e in self.events):
            raise ValueError("所选区间没有基准行情，请更换基准或日期")
        code = request.get("code", "")
        self.manifest = {"name": self.name, "mode": self.mode, "code": code,
                         "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
                         "parameters": request.get("parameters", {}), "config": self.broker.config,
                         "rules": rules, "dataset": self.dataset, "created": now_cn(), "engine": __version__,
                         "rule_engine": RULE_ENGINE_VERSION,
                         "calendar": calendar_manifest(self.broker.teaching_calendar),
                         "model": "快照保守近似 / K线下一柱开盘；不还原队列；日线信号为下一日开盘委托"}
        self.manifest["benchmark_symbol"] = self.benchmark_symbol
        if run_window:
            self.manifest["backtest_window"] = run_window
        if self.input_archive:
            self.manifest["input_archive"] = self.input_archive.manifest
        if live_audit and live_audit["records"]:
            self.manifest["live_rule_observations"] = [live_audit]
        if request.get("learning"):
            self.manifest["learning"] = request["learning"]
        if code:
            self.host = StrategyHost(code, request.get("parameters", {}))
            try:
                result = self.host.call("initialize", self.context())
                self._apply(result)
            except BaseException:
                self.host.close()
                self.host = None
                raise
        self.status = "RUNNING" if request.get("autoplay", True) else "PAUSED"
        self.log("运行已创建；" + ("教学合成数据" if self.dataset and self.dataset["demo"] else "虚拟资金账户"))
        if self.dataset:
            self.log(coverage_text(self.dataset.get("quality")))
            self.log(rules_summary(rules))
        elif self.manifest.get("live_rule_observations"):
            self.log(f"ETF 当前规则已核对，仅适用于 {live_audit['valid_day']}；跨日需更新当日规则后继续。")

    def require_current_live_rules(self):
        audits = self.manifest.get("live_rule_observations")
        if audits and audits[-1]["valid_day"] != now_cn().date().isoformat():
            raise ValueError("ETF 规则已跨日，请点击「更新当日规则」后继续；账户及持仓保留。")

    def refresh_live_rules(self):
        if self.mode not in ("live", "manual") or self.status != "PAUSED":
            raise ValueError("请先暂停实时账户，再更新当日规则")
        from astock.live_rules import extend_live_rules, read_live_rules
        rules, audit = read_live_rules(self.root, list(self.broker.rules), now_cn())
        merged = extend_live_rules(self.broker.rules, rules)
        if audit["records"]:
            audits = self.manifest.setdefault("live_rule_observations", [])
            if not audits or audits[-1]["valid_day"] != audit["valid_day"]:
                audits.append(audit)
        self.broker.rules = merged
        self.manifest["rules"] = merged
        self.control("refresh_live_rules", valid_day=audit["valid_day"], evidence=audit)
        self.log("当日规则已更新；资金和持仓保留，点击「继续」恢复运行。")
        self.dirty = True

    def context(self):
        b = self.broker
        return {"rules": b.context_rules(), "available_cash": b.available_cash, "equity": b.account.equity,
                "clock": b.clock, "history": dict(self.history), "times": self.times,
                "positions": {s: {"quantity": p.quantity, "available": b.available_quantity(s),
                                  "cost": float(p.cost)} for s, p in b.account.positions.items()},
                "orders": [o for o in b.orders if o.active]}

    def log(self, message, values=None):
        item = {"time": self.broker.clock or now_cn(), "message": str(message), "values": values or {}}
        self.logs.append(item)
        self.logs = self.logs[-500:]
        self.journal.append(("log", item))
        self.dirty = True

    def _flush_order_events(self, depth=0, *, callback=True, allow_orders=True):
        if self.notifying_orders:
            return
        self.notifying_orders = True
        notifications = 0
        try:
            while True:
                self.pending_order_events.extend(self.broker.drain_order_events())
                if not self.pending_order_events:
                    break
                order = self.pending_order_events.popleft()
                kind = "order_update" if order.id in self.reported_order_ids else "order"
                self.reported_order_ids.add(order.id)
                self.journal.append((kind, order))
                self.log(f"{order.id} {'买入' if order.side == 'BUY' else '卖出'} {order.symbol}：{order.note}",
                         {"status": order.status, "filled": order.filled, "reason": order.reason})
                if callback and self.host:
                    notifications += 1
                    if notifications > 100:
                        raise RuntimeError("单次订单回报产生过多连续指令，已停止策略")
                    self._apply(self.host.call("on_order", self.context(), order), depth + 1,
                                allow_orders=allow_orders)
        finally:
            self.notifying_orders = False

    def _apply(self, response, depth=0, *, allow_orders=True):
        if depth > 3:
            raise RuntimeError("订单回报递归产生过多指令，已停止策略")
        for record in response.get("explanations", []):
            self.log(record["message"], record.get("values"))
        for command in response.get("commands", []):
            if not allow_orders:
                self.log("策略暂停或停止期间，订单回报只更新策略状态；未执行回调中的交易指令")
                continue
            if command["op"] == "order":
                self.broker.submit(command["symbol"], command["side"], command["quantity"],
                                   command["price"], command.get("reason", ""))
                self._flush_order_events(depth)
            elif command["op"] == "cancel":
                self.broker.cancel(command["order_id"])
                self._flush_order_events(depth)

    def _flush_equity_events(self):
        for entry in self.broker.drain_equity_events():
            self.journal.append(("equity", entry))
            if entry.kind == "entitlement":
                message = (f"{entry.symbol} 权益登记：应收分红 {entry.receivable_delta:.2f} 元，"
                           f"份额变动 {entry.quantity_delta:+d}")
            else:
                message = f"{entry.symbol} 分红到账 {entry.cash_delta:.2f} 元，应收转为可用现金"
            self.log(message, {"action_key": entry.action_key, "pay_date": entry.pay_date,
                               "share_available_date": entry.share_available_date})

    def cancel(self, order_id):
        self.control("cancel", order_id=order_id)
        self.broker.cancel(order_id)
        self._flush_order_events(allow_orders=self.status == "RUNNING")

    def pause(self):
        self.control("pause")
        self.status = "PAUSED"
        if self.mode in ("live", "manual"):
            self.broker.cancel_all("暂停实时策略，撤销未成交委托")
            self._flush_order_events(allow_orders=False)
            self.log("实时策略已暂停并撤单")
        else:
            self.log("回放已暂停，保留委托与冻结资金；单步或继续后从当前时刻推进")

    def control(self, operation, **values):
        if self.input_archive:
            self.journal.append(("control", {"operation": operation, "time": now_cn(),
                                            "after_input": self.input_archive.manifest["count"] +
                                            len(self.input_archive.pending), **values}))

    def event(self, event, live=False):
        b = self.broker
        if live and isinstance(event, Quote):
            event = replace(event, observed=now_cn())
            if self.status == "RUNNING":
                try:
                    self.require_current_live_rules()
                except ValueError as error:
                    self.pause()
                    self.log(str(error))
            if self.input_archive:
                self.input_archive.append(event)
                self.dirty = True  # Persist duplicates too, even if broker ignores them.
        # Recorded account rules carry their actual activation time. A later
        # refresh must not make those rules visible to earlier replay inputs.
        from astock.rules import rule_at
        observed = event_clock(event)
        day = observed.astimezone(CN).date().isoformat()
        rules_waiting = any(r.known_from and rule_at(r, day, observed_at=observed).status == "unknown"
                            for r in b.rules.values())
        if rules_waiting and self.mode in ("backtest", "replay"):
            b.cancel_all("当时 ETF 规则尚未启用；沿用实时账户跨日撤单行为")
        if isinstance(event, CorporateAction):
            b.corporate_action(event)
            self._flush_equity_events()
            self._flush_order_events(allow_orders=False)
            return
        sequence = b.sequence
        fills = b.on_event(event, live_now=event_clock(event) if isinstance(event, Quote) else None)
        self._flush_equity_events()
        if sequence == b.sequence:
            if b.order_events:
                self._flush_order_events(allow_orders=False)
                self.dirty = True
            return
        price = event.last if isinstance(event, Quote) else event.close
        if price <= 0:
            self._flush_order_events(allow_orders=False)
            return
        self.times[event.symbol] = event.time
        indicator = float(price * event.factor) if isinstance(event, Bar) else float(price)
        self.history[event.symbol].append(indicator)
        self.history[event.symbol] = self.history[event.symbol][-2048:]
        point = {"time": event.time, "close": float(price), "open": float(event.open) if isinstance(event, Bar) else float(price),
                 "high": float(event.high) if isinstance(event, Bar) else float(price),
                 "low": float(event.low) if isinstance(event, Bar) else float(price), "volume": event.volume}
        self.prices[event.symbol].append(point)
        self.prices[event.symbol] = self.prices[event.symbol][-2000:]
        for trade in fills:
            self.log(f"{trade.id} 成交 {trade.symbol} {trade.quantity} @ {trade.price}；费用 {trade.fee}",
                     {"reason": trade.reason})
            self.journal.append(("trade", trade))
        # 接收报价并不意味着可交易；过期、非连续竞价和停牌数据不触发策略。
        valid_strategy = not rules_waiting
        if isinstance(event, Quote):
            from astock.rules import continuous_session
            age = (event_clock(event) - event.time).total_seconds()
            valid_strategy &= not event.suspended and continuous_session(event.time, b.rules[event.symbol], teaching=b.teaching_calendar)
            valid_strategy &= continuous_session(event_clock(event), b.rules[event.symbol], teaching=b.teaching_calendar)
            valid_strategy &= -2 <= age <= b.config.stale_seconds
        elif isinstance(event, Bar):
            from astock.rules import continuous_bar
            valid_strategy &= not event.suspended and (event.period == "1d" or continuous_bar(event, b.rules[event.symbol], teaching=b.teaching_calendar))
        valid_strategy &= b.rule(event.symbol).status not in {"unknown", "suspended", "unlisted"}
        self._flush_order_events(allow_orders=self.status == "RUNNING" and valid_strategy)
        if self.host and self.status == "RUNNING" and valid_strategy:
            self._apply(self.host.call("on_quote" if isinstance(event, Quote) else "on_bar", self.context(), event))
        self.dirty = True

    def sample_equity(self):
        b = self.broker
        if not b.clock:
            return
        equity = float(b.account.equity)
        self.peak = max(self.peak, equity)
        event = b.market.get(self.benchmark_symbol)
        price = float(event.last if isinstance(event, Quote) else event.close) if event else None
        if price and self.benchmark_start is None:
            self.benchmark_start = price
        benchmark = float(b.account.initial) * price / self.benchmark_start if price and self.benchmark_start else float(b.account.initial)
        point = {"time": b.clock, "equity": equity, "benchmark": benchmark,
                 "drawdown": 1 - equity / self.peak, "cash": float(b.account.cash),
                 "fees": float(b.account.fees)}
        if self.curve and self.curve[-1]["time"] == point["time"]:
            self.curve[-1] = point
        else:
            self.curve.append(point)

    def step(self):
        if self.index >= len(self.events):
            self.finish()
            return
        # 同一时间的多标的作为一组，避免将不同标的误算为连续时间。
        timestamp = event_clock(self.events[self.index])
        original_status = self.status
        self.status = "RUNNING"
        try:
            while self.index < len(self.events) and event_clock(self.events[self.index]) == timestamp:
                event = self.events[self.index]
                self.event(event)
                self.index += 1
            self.sample_equity()
        finally:
            self.status = original_status
        if self.index == len(self.events):
            self.finish()
        elif self.mode == "replay":
            gap = (event_clock(self.events[self.index]) - timestamp).total_seconds()
            self.next_due = time.monotonic() + min(60, max(0, gap / self.speed))
        else:
            self.next_due = time.monotonic() + .005

    def finish(self):
        self.status = "COMPLETED"
        self.broker.cancel_all("数据结束，撤销剩余委托")
        self._flush_order_events(allow_orders=False)
        self.log("运行完成，结果已保存")
        if self.host:
            self.host.close()
            self.host = None

    def stop(self):
        self.control("stop")
        self.status = "STOPPED"
        self.broker.cancel_all()
        try:
            self._flush_order_events(allow_orders=False)
        except Exception:
            self.log("停止时订单回报异常：" + traceback.format_exc())
            self._flush_order_events(callback=False)
        self.log("已停止并撤销所有未成交委托")
        if self.host:
            self.host.close()
            self.host = None

    def fail(self, error):
        self.status = "ERROR"
        self.broker.cancel_all("策略运行异常，已撤销未成交委托")
        self._flush_order_events(callback=False)
        self.log(str(error))
        self.sample_equity()
        if self.host:
            self.host.close()
            self.host = None

    def result(self):
        return {"curve": self.curve, "logs": self.logs, "prices": dict(self.prices),
                "statistics": performance(self.curve, self.broker), "index": self.index,
                "total": len(self.events), "benchmark_symbol": self.benchmark_symbol}

    def message(self):
        # multiprocessing.Queue pickles on a feeder thread after put() returns.
        # Freeze all nested state now so later quotes cannot make an already
        # committed update advertise fills that have not yet been persisted.
        return deepcopy({"type": "run_update", "id": self.id, "name": self.name, "mode": self.mode,
                "status": self.status, "speed": self.speed, "snapshot": self.broker.snapshot(), "result": self.result(),
                "manifest": self.manifest, "frozen": self.broker.frozen_cash,
                "available": self.broker.available_cash,
                "available_positions": {s: self.broker.available_quantity(s) for s in self.broker.account.positions}})

    def persist(self, store, *, finalize=False):
        if self.input_archive:
            try:
                self.input_archive.flush()
                if finalize or self.status in ("STOPPED", "ERROR", "COMPLETED"):
                    self.manifest["dataset"] = finalize_inputs(self.root, self.input_archive.manifest,
                                                                self.broker.rules, self.name)
                    self.input_archive.manifest["state"] = "closed"
            except Exception as error:
                # Keep an auditable fallback if a Parquet write fails. Never carry
                # on trading while silently dropping the inputs behind fills.
                self.input_archive.manifest["state"] = "error"
                self.input_archive.manifest["error"] = str(error)
                self.journal.extend(("unarchived_input", loads(p)) for p in self.input_archive.pending)
                self.input_archive.pending = []
                self.fail(f"行情留存失败，账户已停止：{error}；未归档输入保存在 SQLite 流水")
                self.input_archive = None
        store.save_run(self.id, self.name, self.mode, self.status, self.manifest, self.broker.snapshot(),
                       self.result(), self.journal)
        self.journal = []
        self.last_save = time.monotonic()


def engine_worker(commands, output, root):
    output.cancel_join_thread()
    store = Store(Path(root))
    runs = {}
    latest_quotes = {}
    # 恢复所有未正常结束的账户，原子取消旧委托。用户必须显式创建新的策略运行。
    for saved in store.runs():
        if saved["status"] in ("RUNNING", "PAUSED"):
            record = store.load_run(saved["id"])
            try:
                recovered = Broker.restore(record["snapshot"])
            except Exception as error:
                # 一个损坏账户不能阻止其他账户与界面启动；保留余额证据，不猜测修复。
                snapshot = record["snapshot"]
                snapshot["accounting_error"] = str(error)
                recovery_log = [("recovery_error", f"账户核对失败，已隔离：{error}")]
                for order in snapshot["orders"]:
                    if order.active:
                        order.status, order.note = "CANCELED", "账户核对失败：取消旧委托，保留原余额供检查"
                        recovery_log.append(("order_update", order))
                store.save_run(saved["id"], saved["name"], saved["mode"], "RECOVERY_ERROR",
                               record["manifest"], snapshot, record["result"], recovery_log)
                continue
            archive = record["manifest"].get("input_archive")
            recovery_log = [("recovery", "恢复账户，取消旧委托；策略保持暂停")]
            if recovered.legacy_equity_unverified:
                from astock.accounting import LEGACY_NOTICE
                recovery_log.append(("recovery_warning", LEGACY_NOTICE))
            recovery_log.extend(("order_update", order) for order in recovered.drain_order_events())
            if archive and archive.get("state") != "error":
                try:
                    record["manifest"]["dataset"] = finalize_inputs(
                        root, archive, recovered.rules, saved["name"])
                    archive["state"] = "recovered"
                except Exception as error:
                    archive["state"], archive["error"] = "error", str(error)
                    recovery_log.append(("recovery_error", f"输入归档不可回放：{error}"))
            store.save_run(saved["id"], saved["name"], saved["mode"], "RECOVERED",
                           record["manifest"], recovered.snapshot(), record["result"],
                           recovery_log)
    output.put({"type": "engine_ready", "runs": store.runs()})
    try:
        while True:
            try:
                request = commands.get(timeout=.01)
            except Empty:
                request = None
            if request:
                try:
                    op = request["op"]
                    run = runs.get(request.get("id"))
                    if op == "shutdown":
                        break
                    if op == "start":
                        if sum(r.status == "RUNNING" for r in runs.values()) >= 8:
                            raise ValueError("最多同时运行 8 个策略账户")
                        run = Run(request, root, output)
                        runs[run.id] = run
                        if run.mode in ("live", "manual"):
                            for q in sorted(latest_quotes.values(), key=lambda q: (q.time, q.symbol)):
                                if q.symbol in run.broker.rules:
                                    run.event(q, live=True)
                            run.sample_equity()
                        run.persist(store)
                        output.put({"type": "run_created", "id": run.id})
                    elif op == "quotes":
                        latest_quotes.update({q.symbol: q for q in request["quotes"]})
                        for candidate in runs.values():
                            if candidate.mode in ("live", "manual") and candidate.status in ("RUNNING", "PAUSED"):
                                try:
                                    for q in request["quotes"]:
                                        if q.symbol in candidate.broker.rules:
                                            candidate.event(q, live=True)
                                    candidate.sample_equity()
                                except Exception:
                                    candidate.fail(traceback.format_exc())
                    elif op == "list":
                        output.put({"type": "run_list", "runs": store.runs()})
                    elif op == "load":
                        if run:
                            run.persist(store)
                            output.put(run.message())
                        else:
                            record = store.load_run(request["id"])
                            meta = next(x for x in store.runs() if x["id"] == request["id"])
                            output.put({"type": "run_update", **meta, **record,
                                        "frozen": 0, "available": record["snapshot"]["account"].cash,
                                        "available_positions": {}})
                    elif run and op == "pause":
                        if run.status == "RUNNING":
                            run.pause()
                    elif run and op == "resume":
                        if run.status == "PAUSED":
                            run.require_current_live_rules()
                            run.control("resume")
                            run.status = "RUNNING"
                            run.next_due = 0
                            run.log("继续运行")
                    elif run and op == "refresh_live_rules":
                        run.refresh_live_rules()
                    elif run and op == "step":
                        if run.status == "PAUSED" and run.mode in ("replay", "backtest"):
                            run.step()
                    elif run and op == "speed":
                        run.speed = max(1, min(1000, float(request["value"])))
                        run.next_due = 0
                    elif run and op == "stop":
                        run.stop()
                    elif run and op == "cancel":
                        run.cancel(request["order_id"])
                    elif run and op == "manual_order":
                        if run.mode != "manual" or run.status != "RUNNING":
                            raise ValueError("请先创建并选择正在运行的手动练习账户")
                        run.require_current_live_rules()
                        # 更新提交时钟，避免在断流时用旧时刻通过新鲜度检查。
                        run.broker.clock = now_cn()
                        run.control("manual_order", order=request["order"])
                        run._apply({"commands": [{"op": "order", **request["order"]}]})
                    elif op not in ("quotes", "list", "load"):
                        raise ValueError("请选择当前会话中可操作的运行；历史记录仅供查看")
                    if run:
                        run.dirty = True
                        run.persist(store)
                except Exception as e:
                    error = traceback.format_exc()
                    if run and op in ("start", "step", "pause", "cancel"):
                        run.fail(error)
                        run.persist(store)
                    output.put({"type": "error", "message": str(e), "traceback": error})
            for run in list(runs.values()):
                if run.status == "RUNNING" and run.mode in ("live", "manual"):
                    try:
                        run.require_current_live_rules()
                    except ValueError as error:
                        try:
                            run.pause()
                            run.log(str(error))
                        except Exception:
                            run.fail(traceback.format_exc())
                            output.put({"type": "error", "message": run.logs[-1]["message"]})
                if run.status == "RUNNING" and run.mode in ("replay", "backtest") and time.monotonic() >= run.next_due:
                    try:
                        run.step()
                    except Exception:
                        run.fail(traceback.format_exc())
                        output.put({"type": "error", "message": run.logs[-1]["message"]})
                if run.dirty and time.monotonic() - run.last_emit > .15:
                    run.persist(store)
                    output.put(run.message())
                    run.last_emit = time.monotonic()
                    run.dirty = False
                if time.monotonic() - run.last_save > 1 and run.status in ("RUNNING", "PAUSED"):
                    run.persist(store)
                elif run.status in ("COMPLETED", "STOPPED", "ERROR") and run.journal:
                    run.persist(store)
    finally:
        for run in runs.values():
            if run.status in ("RUNNING", "PAUSED"):
                run.status = "PAUSED"
                run.broker.cancel_all("程序关闭：撤销委托，恢复时不自动运行")
                run._flush_order_events(callback=False)
                run.control("shutdown")
                run.persist(store, finalize=True)
            if run.host:
                run.host.close()
        store.close()
