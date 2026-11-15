"""Terminal-style backtest overview using the same saved run data as detail tabs."""
from astock.help_registry import help_target
from html import escape

from PySide6 import QtCore, QtWidgets

from astock.ui_components import EquityChart, PriceChart, RecordTable, button, label


class BacktestOverview(QtWidgets.QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.state = None
        self.selected_symbols = {}
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setSpacing(5)
        toolbar.addWidget(label("主图证券"))
        self.symbol_combo = help_target(QtWidgets.QComboBox(), 'backtest_workspace.BacktestOverview.__init__.symbol_combo')
        self.symbol_combo.setMinimumWidth(120)
        toolbar.addWidget(self.symbol_combo)
        self.scope = label("等待回测 · 选择证券查看价格和买卖点", "muted", True)
        toolbar.addWidget(self.scope, 1)
        layout.addLayout(toolbar)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.charts = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.charts.setChildrenCollapsible(False)
        self.price_chart = help_target(PriceChart("价格与买卖点"), 'backtest_workspace.BacktestOverview.__init__.price_chart')
        self.price_chart.setMinimumHeight(155)
        self.price_chart.volume.setMaximumHeight(45)
        self.equity_chart = help_target(EquityChart(), 'backtest_workspace.BacktestOverview.__init__.equity_chart')
        self.equity_chart.setMinimumHeight(145)
        self.equity_chart.drawdown.setMaximumHeight(65)
        self.charts.addWidget(self.price_chart)
        self.charts.addWidget(self.equity_chart)
        self.charts.setSizes([310, 190])
        self.splitter.addWidget(self.charts)

        side = QtWidgets.QWidget()
        side.setMinimumWidth(210)
        side.setMaximumWidth(340)
        side_layout = QtWidgets.QVBoxLayout(side)
        side_layout.setContentsMargins(4, 0, 0, 0)
        side_layout.setSpacing(4)
        side_layout.addWidget(label("绩效分析 · 当前运行", "title"))
        self.performance = help_target(QtWidgets.QTableWidget(8, 2), 'backtest_workspace.BacktestOverview.__init__.performance')
        self.performance.setHorizontalHeaderLabels(["指标", "数值"])
        self.performance.verticalHeader().hide()
        self.performance.verticalHeader().setDefaultSectionSize(24)
        self.performance.setAlternatingRowColors(True)
        self.performance.setShowGrid(False)
        self.performance.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.performance.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.performance.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.performance.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.performance.setMinimumHeight(200)
        self.performance.setMaximumHeight(250)
        self.metrics = (
            ("equity", "总权益", "money", "现金、持仓市值及已确认应收权益的合计。"),
            ("return", "累计收益", "percent", "相对本次运行初始资金的收益。"),
            ("benchmark_return", "价格基准收益", "percent", "所选基准的价格收益，不含分红再投资及交易费用。"),
            ("max_drawdown", "最大回撤", "percent", "当前观察范围内从此前最高权益下降的最大比例。"),
            ("fees", "累计费用", "money", "本次运行已经记账的交易费用。"),
            ("trades", "成交笔数", "count", "按成交记录统计；部分成交可形成多笔记录。"),
            ("realized", "已实现盈亏", "money", "引擎账本记录的已实现盈亏，不等于账户总收益。"),
            ("profitable_sells", "盈利卖出占比", "percent", "盈利卖出成交记录数 / 全部卖出成交记录数；不是完整买卖回合的胜率。"),
        )
        for row, (_, title, _, explanation) in enumerate(self.metrics):
            item = QtWidgets.QTableWidgetItem(title)
            item.setToolTip(explanation)
            self.performance.setItem(row, 0, item)
            item = QtWidgets.QTableWidgetItem("—")
            item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            item.setToolTip(explanation)
            self.performance.setItem(row, 1, item)
        side_layout.addWidget(self.performance)
        side_layout.addWidget(label("所选证券成交 · 点击查看原因", "muted"))
        self.trades = help_target(RecordTable(
            ["时间", "方向", "数量", "价格"],
            lambda trade: [trade.time.strftime("%m-%d %H:%M"), "买" if trade.side == "BUY" else "卖",
                           trade.quantity, str(trade.price)], [90, 42, 55, 64]), 'backtest_workspace.BacktestOverview.__init__.trades')
        self.trades.setMinimumHeight(80)
        self.trades.setMaximumHeight(160)
        self.trades.itemSelectionChanged.connect(self.select_trade)
        side_layout.addWidget(self.trades, 1)
        self.guidance = help_target(QtWidgets.QTextBrowser(), 'backtest_workspace.BacktestOverview.__init__.guidance')
        self.guidance.setMinimumHeight(55)
        self.guidance.setMaximumHeight(100)
        self.guidance.setHtml("<b>读图顺序</b><p>先看价格上的买卖点，再看下方权益与回撤，最后核对右侧绩效。"
                              "点击成交明细可在详情页追溯策略原因。</p><p>完成回测后，这里显示实际数据范围说明。</p>")
        side_layout.addWidget(self.guidance, 1)
        side_layout.addWidget(help_target(button("分月收益与回撤诊断", self.show_diagnostics), 'backtest_workspace.BacktestOverview.__init__.button'))
        side_layout.addWidget(help_target(button("回测使用教程", self.open_practice), 'backtest_workspace.BacktestOverview.__init__.button2'))
        self.splitter.addWidget(side)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([800, 245])
        layout.addWidget(self.splitter, 1)
        self.symbol_combo.currentTextChanged.connect(self.select_symbol)
        window.chart_symbol.currentTextChanged.connect(self.sync_symbol)
        self.theme(getattr(window, "theme_name", "dark"))

    def show_diagnostics(self):
        self.window.result_tabs.setCurrentWidget(self.window.diagnostics)

    def open_practice(self):
        self.window.replay_usage_tutorial(start_chapter='回测准备')

    def theme(self, name):
        self.price_chart.theme(name)
        self.equity_chart.theme(name)

    def select_symbol(self, symbol):
        if not self.state or symbol not in self.state["result"]["prices"]:
            return
        self.selected_symbols[self.state["id"]] = symbol
        if self.window.chart_symbol.findText(symbol) >= 0:
            self.window.chart_symbol.setCurrentText(symbol)
        self.refresh_price()

    def sync_symbol(self, symbol):
        if self.state and symbol in self.state["result"]["prices"]:
            self.symbol_combo.setCurrentText(symbol)

    def refresh_price(self):
        if not self.state:
            return
        symbol = self.symbol_combo.currentText()
        points = self.state["result"]["prices"].get(symbol, [])
        self.price_chart.set_data(points, self.state["snapshot"]["trades"], symbol,
                                  quote=self.state["mode"] != "backtest", meta=self.state.get('manifest', {}).get('dataset'))
        self.trades.set_records([trade for trade in self.state["snapshot"]["trades"] if trade.symbol == symbol],
                                (self.state["id"], symbol))
        self.scope.setText(f"主图 {len(points):,} 个可用观察值 · 下方为整个账户的权益与回撤")

    def select_trade(self):
        trade = self.trades.current_record()
        if trade is None:
            return
        target = self.window.trades_table
        for index, record in enumerate(target.record_model.records):
            if record.id == trade.id:
                blocker = QtCore.QSignalBlocker(target)
                target.selectRow(index)
                del blocker
                self.window.select_trade(target)
                return

    def update_state(self, state):
        self.state = state
        if state is None:
            self.symbol_combo.clear()
            self.price_chart.set_data([])
            self.equity_chart.set_data([])
            self.trades.set_records([], None)
            for row in range(self.performance.rowCount()):
                self.performance.item(row, 1).setText("—")
            self.scope.setText("等待回测 · 尚未创建本次账户")
            self.guidance.setHtml("<p>准备数据并运行回测后显示当前账户结果。</p>")
            return
        result = state["result"]
        symbols = list(result["prices"])
        chosen = self.selected_symbols.get(state["id"])
        if chosen not in symbols:
            chosen = self.window.chart_symbol.currentText()
        if chosen not in symbols:
            chosen = symbols[0] if symbols else ""
        blocker = QtCore.QSignalBlocker(self.symbol_combo)
        if [self.symbol_combo.itemText(i) for i in range(self.symbol_combo.count())] != symbols:
            self.symbol_combo.clear()
            self.symbol_combo.addItems(symbols)
        self.symbol_combo.setCurrentText(chosen)
        del blocker
        self.selected_symbols[state["id"]] = chosen
        if chosen and self.window.chart_symbol.findText(chosen) >= 0:
            self.window.chart_symbol.setCurrentText(chosen)
        self.refresh_price()
        self.equity_chart.set_data(result["curve"])
        stats = result["statistics"]
        for row, (key, _, kind, _) in enumerate(self.metrics):
            value = stats.get(key)
            if value is None:
                text = "—"
            elif kind == "percent":
                text = f"{value:.2%}"
            elif kind == "count":
                text = f"{value:,}"
            else:
                text = f"{value:,.2f}"
            self.performance.item(row, 1).setText(text)
        meta = state["manifest"].get("dataset") or {}
        from astock.data_identity import source_summary
        source = source_summary(meta)
        self.guidance.setHtml(
            f"<b>{escape(source)}</b><p>价格主图展示所选证券的可用观察窗口，不保证覆盖整个回测。"
            "权益图和右侧绩效属于整个账户；切换主图证券不会改变绩效。</p>"
            "<p>盈利卖出占比按卖出成交记录统计，不是完整买卖回合胜率。"
            "选中成交明细可查看精确时刻与策略解释。</p>")


def build_overview(window):
    return BacktestOverview(window)
