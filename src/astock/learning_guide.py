"""Evidence-backed course progress; offline practice never counts as online access."""
from datetime import datetime, timedelta
import uuid

from astock.datasets import list_datasets, write_dataset
from astock.domain import CN, Quote, dec
from astock.strategy import TEMPLATES


CHECKS = {
    0: [("loaded", "载入合成快照"), ("order", "观察报价与待成交委托"),
        ("fill", "下一条行情产生实际模拟成交"), ("trade", "点击成交查看理由")],
    1: [("loaded", "打开双均线教学副本"), ("changed", "修改有效的快慢周期"), ("saved", "保存修改后的参数")],
    2: [("finished", "完成教学回测"), ("metrics", "查看收益与回撤"), ("trade", "点击成交并定位图表")],
    3: [("quote", "观察行情来源"), ("account", "建立独立虚拟账户"), ("stopped", "停止策略并撤销未成交委托")],
}

QUOTE_CODE = '''# 合成教学快照，不是实际证券历史；演示下一条行情才能成交。
PARAMETERS = {
    "pending": {"type": "bool", "default": False, "label": "保留一笔等待撤销的委托",
                "help": "第四课离线演练开启此项，用低于卖一的限价练习停止并撤单。"}
}
class UserStrategy(Strategy):
    def initialize(self, ctx):
        self.sent = False
    def on_quote(self, ctx, quote):
        if not self.sent:
            self.sent = True
            ctx.explain("教学：观察报价后提交限价委托，最早下一条行情成交",
                        latest=quote.last, bid=quote.bid, ask=quote.ask,
                        visible_ask=quote.ask_size, cumulative_volume=quote.volume, source_time=quote.time)
            ctx.order(quote.symbol, 'BUY', 100, 10.05, '卖一 10.00，限价 10.05；等待下一条有效行情')
            if ctx.parameters['pending']:
                ctx.order(quote.symbol, 'BUY', 100, 9.00, '限价 9.00 低于卖一，留待停止时撤销')
'''


def ensure_quote_lesson(root):
    found = next((m for m in list_datasets(root) if m["source"] == "astock-order-lesson-v1"), None)
    if found:
        return found
    at = datetime(2026, 11, 13, 10, tzinfo=CN)
    quotes = [Quote("600000.SH", at + timedelta(seconds=5*i), at + timedelta(seconds=5*i),
                    dec(10), dec("9.99"), dec(10), 10000, 10000, 100000 + i * 10000,
                    dec(10), dec(11), dec(9), "订单教学", "synthetic-teaching") for i in range(30)]
    return write_dataset(root, "教学 · 两步观察订单与成交", quotes, demo=True, source="astock-order-lesson-v1",
                         verified=True, notes="人工构造的 30 条快照；第 1 条提交，第 2 条可成交。非真实历史，不评价收益。")


class LearningGuide:
    def __init__(self, window):
        self.window = window
        saved = window.store.setting("course_practice_v1", {})
        self.records = {}
        if isinstance(saved, dict):
            for index, checks in CHECKS.items():
                row = saved.get(str(index))
                if isinstance(row, dict) and isinstance(row.get("steps"), list):
                    self.records[str(index)] = {**row, "steps": [key for key, _ in checks if key in row["steps"]]}
        self.lesson = None
        self.attempt = self.run_id = self.expected_mode = self.dataset = self.strategy_name = None
        self.route = "offline"
        evidence = self.records.get("1", {}).get("evidence", {})
        saved_parameters = evidence.get("saved", {}) if isinstance(evidence, dict) else {}
        self.ma_name = saved_parameters.get("strategy") if isinstance(saved_parameters, dict) else None
        if not isinstance(self.ma_name, str):
            self.ma_name = None
        self.last_state = None
        self.message = ""

    def steps(self, lesson):
        record = self.records.get(str(lesson), {})
        return set(record.get("steps", [])) if isinstance(record, dict) else set()

    def complete(self, lesson):
        return all(key in self.steps(lesson) for key, _ in CHECKS[lesson])

    def achieved(self, lesson):
        prior = self.records.get(str(lesson), {}).get("previous_completion", {})
        return self.complete(lesson) or (isinstance(prior, dict) and
                isinstance(prior.get("steps"), list) and
                all(key in prior.get("steps", []) for key, _ in CHECKS[lesson]))

    def mark(self, key, **evidence):
        if self.lesson is None or key in self.steps(self.lesson):
            return
        record = self.records.setdefault(str(self.lesson), {"steps": [], "route": self.route})
        record["steps"].append(key)
        record.setdefault("evidence", {})[key] = evidence
        self.window.store.set_setting("course_practice_v1", self.records)
        self.render()

    def install(self, name, code, values=None):
        w = self.window
        w.save_strategy(quiet=True)
        w.current_template = name
        w.strategy_title.setText(name)
        w.strategy_description.setText("教学副本 · 原策略已保存，可从左侧重新打开")
        w.editor.setPlainText(code)
        w.rebuild_parameters(values=values)
        self.strategy_name = name
        w.active_id = None

    def begin(self, lesson, offline=False):
        w = self.window
        if w.start_pending:
            w.statusBar().showMessage("账户正在创建，请稍候再切换练习。", 6000)
            return
        w.learning_sections.setCurrentIndex(0)
        self.lesson, self.attempt, self.run_id = lesson, uuid.uuid4().hex, None
        self.route = "offline" if lesson != 3 or offline else "online"
        self.last_state, self.message = None, ""
        old = self.records.get(str(lesson), {})
        previous = {key: old[key] for key in ("steps", "route", "attempt", "evidence") if key in old} if self.complete(lesson) else old.get("previous_completion", {})
        self.records[str(lesson)] = {"steps": [], "route": self.route, "attempt": self.attempt,
                                     "previous_completion": previous}
        w.store.set_setting("course_practice_v1", self.records)
        if lesson == 0 or (lesson == 3 and offline):
            meta = ensure_quote_lesson(w.root / "datasets")
            name = ("教学 · 订单观察 " if lesson == 0 else "教学 · 停止与撤单 ") + self.attempt[:8]
            self.install(name, QUOTE_CODE, {"pending": lesson == 3})
            w.refresh_library()
            w.dataset_combo.setCurrentIndex(w.dataset_combo.findData(meta["id"]))
            self.expected_mode, self.dataset = "replay", meta["id"]
            w.mode_combo.setCurrentIndex(w.mode_combo.findData("replay"))
            # The exercise declares its own defaults; original runs retain their saved settings.
            w.capital.setValue(100000)
            w.participation.setValue(10)
            w.slippage.setValue(1)
            w.speed_combo.setCurrentIndex(w.speed_combo.findData(1))
            w.bottom_dock.show()
            w.bottom_tabs.setCurrentIndex(1)
            w.switch_workspace(0)
            if lesson == 0:
                self.mark("loaded", dataset=meta["id"])
        elif lesson == 1:
            self.ma_name = "教学 · 双均线参数 " + self.attempt[:8]
            self.install(self.ma_name, TEMPLATES["双均线趋势"]["code"])
            w._select_demo("bar")
            self.expected_mode, self.dataset = None, None
            w.switch_workspace(0)
            self.focus_parameters()
            self.mark("loaded", strategy=self.ma_name)
        else:
            if not w.current_template.startswith("教学 · 双均线参数"):
                saved = next((row for row in w.store.strategies() if row["name"] == self.ma_name), None)
                self.ma_name = self.ma_name or "教学 · 双均线参数 " + self.attempt[:8]
                self.install(self.ma_name, saved["code"] if saved else TEMPLATES["双均线趋势"]["code"],
                             saved["parameters"] if saved else None)
            self.strategy_name = w.current_template
            w.active_id = None
            if lesson == 2:
                w._select_demo("bar")
                self.expected_mode, self.dataset = "backtest", w.dataset_combo.currentData()
                w.speed_combo.setCurrentIndex(w.speed_combo.findData(1000))
                w.start_run()
            else:
                self.expected_mode, self.dataset = "live", None
                w.mode_combo.setCurrentIndex(w.mode_combo.findData("live"))
                w.switch_workspace(2)
        w.clear_run_selection()
        w.guide_strip.show()
        w.lesson_resume_guide.show()
        self.render()

    def tag_request(self, request):
        if (self.lesson is not None and self.run_id is None and self.expected_mode == request["mode"]
                and request["name"] == self.strategy_name
                and (self.dataset is None or request["dataset"] == self.dataset)):
            request["learning"] = {"lesson": self.lesson, "attempt": self.attempt, "route": self.route}

    def parameters_changed(self):
        w = self.window
        if self.lesson != 1 or w.current_template != self.strategy_name:
            return
        params = w.parameter_values()
        valid = 1 <= params.get("fast", 0) < params.get("slow", 0)
        changed = params.get("fast") != 5 or params.get("slow") != 20
        if valid and changed:
            self.mark("changed", parameters=params)
        self.render()

    def saved(self):
        w = self.window
        if self.lesson == 1 and w.current_template == self.strategy_name:
            params = w.parameter_values()
            if 1 <= params.get("fast", 0) < params.get("slow", 0) and (params.get("fast") != 5 or params.get("slow") != 20):
                self.mark("changed", parameters=params)
                self.mark("saved", strategy=w.current_template, parameters=params)

    def observe_quotes(self, quotes):
        if self.lesson == 3 and self.route == "online" and quotes:
            self.mark("quote", source=quotes[0].source, source_time=quotes[0].time,
                      note="仅证明收到来源报价，不代表盘中刷新稳定性")

    def observe(self, state):
        tag = state.get("manifest", {}).get("learning", {})
        if self.lesson is None or tag.get("attempt") != self.attempt:
            return
        if self.run_id is not None and state["id"] != self.run_id:
            return
        self.run_id, self.last_state = state["id"], state
        snapshot = state["snapshot"]
        if self.lesson == 0:
            if snapshot["orders"] and snapshot["clock"]:
                self.mark("order", run=state["id"])
            if snapshot["trades"]:
                self.mark("fill", run=state["id"], trade=snapshot["trades"][0].id)
        elif self.lesson == 2 and state["status"] == "COMPLETED":
            self.mark("finished", run=state["id"], parameters=state["manifest"]["parameters"])
        elif self.lesson == 3:
            self.mark("account", run=state["id"], mode=state["mode"])
            if self.route == "offline" and snapshot["clock"]:
                self.mark("quote", run=state["id"], note="合成快照回放；尚未接入在线行情")
            if state["status"] == "STOPPED" and not any(order.active for order in snapshot["orders"]):
                if self.route == "online" or any(order.status == "CANCELED" for order in snapshot["orders"]):
                    self.mark("stopped", run=state["id"], canceled=sum(order.status == "CANCELED" for order in snapshot["orders"]))
        self.render()

    def reviewed_trade(self, run_id, trade_id):
        if self.lesson in (0, 2) and run_id == self.run_id:
            self.mark("trade", run=run_id, trade=trade_id)

    def focus_parameters(self):
        w = self.window
        w.open_strategy_editor()
        w.editor_settings.setCurrentIndex(1)
        widget = w.parameters.get("fast")
        if widget:
            w.parameter_scroll.ensureWidgetVisible(widget)
            widget.setFocus()
            widget.selectAll()

    def instruction(self):
        w = self.window
        steps = self.steps(self.lesson)
        if self.complete(self.lesson):
            return ("本节实作已完成。" + ("离线演练不代表已连接真实行情。" if self.lesson == 3 and self.route == "offline" else ""), "返回课程", "course")
        if self.run_id and w.active_id != self.run_id:
            return "当前显示的是其他账户，请返回本节练习账户。", "返回练习账户", "account"
        if self.last_state and self.last_state["status"] in ("ERROR", "RECOVERY_ERROR"):
            return "练习运行异常，请查看日志；修正后可在课程页重做本节。", "查看日志", "logs"
        if self.last_state and self.last_state["status"] == "STOPPED" and (self.lesson in (0, 2) or self.route == "offline"):
            return "本节尚未完成便停止了，可重新开始；已完成的其他课程保留。", "重新开始本节", "restart"
        if self.lesson == 0:
            if "order" not in steps:
                return "点击单步，观察第 1 条报价并提交委托。此时不应成交。", "单步：观察委托", "step"
            if "fill" not in steps:
                return "报价：买一 9.99、卖一 10.00；限价 10.05 的委托正在等待。再推进一条行情观察成交。", "单步：观察成交", "step"
            return "底部切到成交，点击一行查看成交时刻与下单理由。", "打开成交列表", "trades"
        if self.lesson == 1:
            if "changed" not in steps:
                return "右侧将快周期由 5 改为 10，保持慢周期 20。原策略已保存，当前编辑的是教学副本。", "定位快周期", "parameters"
            values = w.parameter_values()
            if not 1 <= values.get("fast", 0) < values.get("slow", 0):
                return "快周期必须小于慢周期，请修正后再保存。", "定位参数", "parameters"
            if values.get("fast") == 5 and values.get("slow") == 20:
                return "当前又回到了默认周期；修改周期后保存，下一课会沿用它。", "定位参数", "parameters"
            return "保存修改后的周期；进入第三课会保留这些参数。", "保存参数", "save"
        if self.lesson == 2:
            if "finished" not in steps:
                if self.last_state and self.last_state["status"] == "PAUSED":
                    return "回测已暂停，可继续观察，结束后再阅读结果。", "继续回测", "resume"
                if self.last_state and self.last_state["status"] == "STOPPED":
                    return "回测提前停止，可以保留当前参数重新运行本节。", "重新回测", "restart"
                return "正在使用上一课参数回测，账户与之前运行独立。", "查看回测进度", "analysis"
            if "metrics" not in steps:
                return "观察收益、最大回撤与手续费；合成样本结果不说明实际策略收益。", "查看收益与回撤", "metrics"
            return "点击底部成交记录，在图表上定位买卖点并阅读理由。", "打开成交列表", "trades"
        if self.route == "offline":
            if "quote" not in steps:
                return "离线演练：使用合成报价建立独立回放账户，不连接网络。", "单步：读取合成报价", "step"
            if not self.last_state["snapshot"]["trades"]:
                return "第一笔委托等待下一条报价；另一笔低价委托会继续等待。", "单步：观察成交", "step"
            return "还有一笔限价 9.00 的未成交委托。停止后应撤单并释放冻结资金。", "停止练习并撤单", "stop"
        if "quote" not in steps:
            return "连接真实行情，检查来源时间。无网络可返回课程选择离线演练。", "连接 / 重试行情", "connect"
        if "account" not in steps:
            return "已收到来源报价。创建虚拟账户；盘后报价不会触发成交。", "启动策略仿真", "live"
        return "观察虚拟账户与行情状态，结束时停止并撤销未成交委托。", "停止策略并撤单", "stop"

    def act(self):
        if self.lesson is None:
            return
        w = self.window
        _, _, action = self.instruction()
        if action in ('step', 'resume', 'stop') and self.run_id in w.states:
            state = w.states[self.run_id]
            destination = 1 if state.get('mode') in ('backtest', 'replay') else 2
            if w.pages.currentIndex() != destination:
                w.select_run(self.run_id)
        if action == "course":
            w.show_lesson(self.lesson)
            w.open_practice()
        elif action == "account":
            w.view_saved_run(self.run_id)
        elif action == "logs":
            w.bottom_dock.show()
            w.bottom_tabs.setCurrentIndex(3)
        elif action == "step":
            w.step_run()
        elif action == "parameters":
            self.focus_parameters()
        elif action == "save":
            w.save_strategy()
        elif action in ("analysis", "metrics"):
            w.switch_workspace(1)
            w.result_tabs.setCurrentIndex(0)
            if action == "metrics":
                self.mark("metrics", run=self.run_id)
        elif action == "trades":
            w.bottom_dock.show()
            w.bottom_tabs.setCurrentIndex(2)
            w.switch_workspace(1)
        elif action == "resume":
            w.send_run("resume")
        elif action == "restart":
            self.begin(self.lesson, offline=self.route == "offline")
        elif action == "stop":
            w.send_run("stop")
        elif action == "connect":
            if w.connected:
                w.toggle_market()
            w.toggle_market()
        elif action == "live":
            w.start_live(False)

    def render(self):
        w = self.window
        count = sum(self.achieved(index) for index in CHECKS)
        w.lesson_progress.setText(f"已读 {len(w.completed)} / 4 · 实作 {count} / 4")
        selected = w.lesson_index
        steps = self.steps(selected)
        text = "  →  ".join(("✓ " if key in steps else "○ ") + title for key, title in CHECKS[selected])
        record = self.records.get(str(selected), {})
        if selected == 3 and record.get("route") == "offline":
            text += "\n离线演练记录：使用合成快照；在线行情连接尚未由本次练习验证。"
        if not self.complete(selected) and self.achieved(selected):
            text += "\n上次完成记录已保留；以上为本次重做的进度。"
        w.lesson_steps.setText(text)
        if self.lesson is not None:
            instruction, title, _ = self.instruction()
            w.guide_text.setText(f"第 {self.lesson + 1} 课 · " + instruction)
            w.guide_next.setText(title)
            w.guide_next.setEnabled(not w.start_pending)
            if hasattr(w, "strategy_dialog"):
                w.strategy_dialog.guide_text.setText(w.guide_text.text())
                w.strategy_dialog.guide_button.setText(title)
                w.strategy_dialog.guide_button.setEnabled(not w.start_pending)
