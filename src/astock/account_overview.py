"""Read-only, per-account overview; selecting an account never loads the engine."""
from astock.help_registry import help_target
from PySide6 import QtCore, QtWidgets

from astock.broker import Broker
from astock.model_trading import STATUS
from astock.reports import log_message
from astock.ui_components import button, label, populate, table


MODES = {"live": "实时仿真", "manual": "手动练习", "backtest": "历史回测", "replay": "快照回放"}
ORDER_STATUS = {"OPEN": "待成交", "PARTIAL": "部分成交", "FILLED": "已成交", "CANCELED": "已撤单", "REJECTED": "已拒单"}


class AccountOverview(QtWidgets.QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.entries = {}
        self.selected = window.store.setting("home_account", None)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(label("历史记录（只读）"))
        self.selector = help_target(QtWidgets.QComboBox(), 'account_overview.AccountOverview.__init__.selector')
        self.selector.setMinimumContentsLength(24)
        row.addWidget(self.selector, 1)
        row.addWidget(help_target(button("刷新", self.refresh), 'account_overview.AccountOverview.__init__.button'))
        self.details = help_target(button("查看账户详情", self.open_details), 'account_overview.AccountOverview.__init__.details')
        row.addWidget(self.details)
        layout.addLayout(row)
        actions = QtWidgets.QHBoxLayout()
        self.report_button = help_target(button("导出所选报告", self.export_selected), 'account_overview.AccountOverview.__init__.report_button')
        self.compare_button = help_target(button("运行对比", window.compare_runs), 'account_overview.AccountOverview.__init__.compare_button')
        actions.addWidget(self.report_button)
        actions.addWidget(self.compare_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.note = label("", "muted", True)
        layout.addWidget(self.note)
        grid = QtWidgets.QGridLayout()
        self.values = {}
        for i, title in enumerate(("总资产", "可用资金", "冻结资金", "持仓市值", "浮动盈亏", "累计收益")):
            box = QtWidgets.QVBoxLayout()
            box.addWidget(label(title, "muted"))
            self.values[title] = label("—", "title")
            box.addWidget(self.values[title])
            grid.addLayout(box, i // 3, i % 3)
        layout.addLayout(grid)
        self.tabs = help_target(QtWidgets.QTabWidget(), 'account_overview.AccountOverview.__init__.tabs')
        self.positions = help_target(table(["证券", "持仓", "可卖", "成本金额", "估值价格", "持仓市值", "浮动盈亏"]), 'account_overview.AccountOverview.__init__.positions')
        self.operations = help_target(table(["时间", "类型", "证券", "方向 / 状态", "数量", "价格", "说明"]), 'account_overview.AccountOverview.__init__.operations')
        self.logs = help_target(table(["时间", "运行记录"]), 'account_overview.AccountOverview.__init__.logs')
        self.tabs.addTab(self.positions, "持仓")
        self.tabs.addTab(self.operations, "最近操作")
        self.tabs.addTab(self.logs, "运行日志")
        self.manifest = help_target(QtWidgets.QTextBrowser(), 'account_overview.AccountOverview.__init__.manifest')
        self.tabs.addTab(self.manifest, "保存的策略与配置")
        layout.addWidget(self.tabs, 1)
        self.empty = label("", "muted", True)
        layout.addWidget(self.empty)
        self.selector.currentIndexChanged.connect(self.select_account)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(lambda: self.refresh() if self.isVisible() else None)
        self.timer.start()
        self.refresh()

    def refresh(self):
        self.entries = {r["id"]: r for r in self.window.store.runs()}
        for identity, state in self.window.states.items():
            self.entries[identity] = {**self.entries.get(identity, {}), **state}
        if self.selected not in self.entries:
            self.selected = next((key for key, r in self.entries.items() if r["mode"] in ("live", "manual")),
                                 next(iter(self.entries), None))
        items = [(f"{MODES.get(r['mode'], r['mode'])} · {r['name']} · {key}", key)
                 for key, r in self.entries.items()]
        if items != [(self.selector.itemText(i), self.selector.itemData(i)) for i in range(self.selector.count())]:
            with QtCore.QSignalBlocker(self.selector):
                self.selector.clear()
                for title, identity in items:
                    self.selector.addItem(title, identity)
                self.selector.setCurrentIndex(self.selector.findData(self.selected))
        self.render()

    def select_account(self, *_):
        self.selected = self.selector.currentData()
        self.window.store.set_setting("home_account", self.selected)
        self.render()

    def render(self):
        for value in self.values.values():
            value.setText("—")
        for widget in (self.positions, self.operations, self.logs):
            populate(widget, [])
        self.tabs.setTabText(0, "持仓（0）")
        self.tabs.setTabText(1, "最近操作（0）")
        entry = self.entries.get(self.selected)
        self.details.setEnabled(entry is not None)
        self.report_button.setEnabled(entry is not None)
        self.manifest.clear()
        self.empty.setText("")
        if entry is None:
            self.note.setText("尚无账户。到模拟交易创建仿真 / 手动账户，或完成一次回测后在此查看。")
            return
        state = self.window.states.get(self.selected)
        if not state or "snapshot" not in state:
            try:
                state = self.window.store.load_run(self.selected)
            except ValueError:
                state = {}
        from html import escape
        from astock.domain import dumps
        config = state.get('manifest', {})
        from astock.data_identity import display_name, source_summary
        data_description = (display_name(config['dataset']) if config.get('dataset') else
                            '真实行情 · 本地虚拟账户' if entry['mode'] in ('live', 'manual') else '数据来源未记录')
        self.manifest.setHtml('<h3>保存时的策略与参数</h3><p>' + escape(source_summary(config.get('dataset'))) +
                             '</p><pre>' + escape(dumps(config)) + '</pre>')
        self.details.setText('打开回测结果' if entry['mode'] in ('backtest', 'replay') else '进入模拟控制')
        snapshot = state.get("snapshot", {})
        account = snapshot.get("account")
        clock = snapshot.get("clock")
        stamp = clock.strftime("%Y-%m-%d %H:%M:%S") if clock else "尚无行情时点"
        self.note.setText(f"本地虚拟账户 · {MODES.get(entry['mode'], entry['mode'])} · "
                          f"{STATUS.get(entry['status'], entry['status'])} · 估值时点 {stamp}。金额单位：元。各账户独立记账。\n{data_description}")
        if account is None:
            self.empty.setText("此账户暂无可用快照，资金与持仓暂不显示。")
            return
        self.empty.setText("最近操作：按成交 / 委托提交时间倒序显示 50 条；委托状态取当前快照。估值价格不代表实时行情。")
        # Reuse broker calculations without restore(), which cancels pending orders.
        available, frozen, quantities = None, None, {}
        try:
            broker = Broker(snapshot["rules"], account.initial, snapshot["config"])
            broker.account, broker.orders = account, snapshot["orders"]
            broker.day, broker.clock = snapshot["day"], clock
            available, frozen = broker.available_cash, broker.frozen_cash
            quantities = {s: broker.available_quantity(s) for s in account.positions}
        except (KeyError, ValueError):
            self.empty.setText("快照规则不完整，可用资金、冻结及可卖数量暂不可核验。")
        market_value = sum(p.quantity * p.last for p in account.positions.values())
        floating = sum(p.quantity * p.last - p.cost for p in account.positions.values() if p.quantity)
        for title, value in zip(self.values, (account.equity, available, frozen, market_value, floating,
                                             account.equity - account.initial)):
            self.values[title].setText(f"{value:,.2f}" if value is not None else "—")
        populate(self.positions, [[s, p.quantity, quantities.get(s, "—"), f"{p.cost:,.2f}",
                                  f"{p.last:,.3f}", f"{p.quantity * p.last:,.2f}",
                                  f"{p.quantity * p.last - p.cost:+,.2f}"]
                                 for s, p in account.positions.items() if p.quantity])
        records = []
        for trade in snapshot.get("trades", []):
            records.append((trade.time, "成交", trade.symbol, "买入" if trade.side == "BUY" else "卖出",
                            trade.quantity, str(trade.price), trade.reason))
        for order in snapshot.get("orders", []):
            records.append((order.created, "委托", order.symbol,
                            ("买入" if order.side == "BUY" else "卖出") + " · " + ORDER_STATUS.get(order.status, order.status),
                            order.quantity, str(order.price), order.note or order.reason))
        records.sort(key=lambda row: row[0], reverse=True)
        populate(self.operations, [[r[0].strftime("%Y-%m-%d %H:%M:%S"), *r[1:]] for r in records[:50]])
        logs = sorted(state.get("result", {}).get("logs", []), key=lambda r: r["time"], reverse=True)[:50]
        populate(self.logs, [[r["time"].strftime("%Y-%m-%d %H:%M:%S"), log_message(r)] for r in logs])
        self.tabs.setTabText(0, f"持仓（{self.positions.rowCount()}）")
        self.tabs.setTabText(1, f"最近操作（{min(len(records), 50)}）")
        if not self.positions.rowCount():
            self.empty.setText("当前账户空仓。" + self.empty.text())

    def export_selected(self):
        entry = self.entries.get(self.selected)
        if entry:
            self.window.show_operation('report', self.selected, entry['name'])

    def open_details(self):
        if self.selected in self.entries:
            self.window.select_run(self.selected)
