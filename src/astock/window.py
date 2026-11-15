from __future__ import annotations
from astock.help_registry import help_target

import ast
import multiprocessing as mp
from pathlib import Path
from queue import Empty
import re
import time

from PySide6 import QtCore, QtGui, QtWidgets

from astock.datasets import DEMO_BAR_SOURCE, DEMO_QUOTE_SOURCE, ensure_demo, list_datasets
from astock.data_identity import display_name, is_index, origin_label, source_summary
from astock.data_jobs import DataJobs, publish_import
from astock.data_quality import coverage_text
from astock.domain import MatchConfig, dec, now_cn, symbol_code
from astock.engine import engine_worker
from astock.learning import GLOSSARY, LESSONS
from astock.market import download_history_worker, market_worker
from astock.reports import EQUITY_HEADERS, accounting_note, equity_row, log_message
from astock.storage import Store
from astock.strategy import TEMPLATES, parameter_schema
from astock.ui_components import INITIAL_CAPITAL_RANGE, CodeEditor, EquityChart, PriceChart, RecordTable, WorkspaceStack, button, label, populate, stylesheet, table

STATUS = {"OPEN": "待成交", "PARTIAL": "部分成交", "FILLED": "已成交", "CANCELED": "已撤单", "REJECTED": "已拒单",
          "RUNNING": "运行中", "PAUSED": "已暂停", "COMPLETED": "已完成", "STOPPED": "已停止",
          "ERROR": "运行异常", "RECOVERED": "恢复 · 未运行", "RECOVERY_ERROR": "恢复核对失败"}
MODES = {"backtest": "历史回测", "replay": "快照回放", "live": "实时仿真", "manual": "手动练习"}


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, root, start_workers=True):
        super().__init__()
        self.root = Path(root)
        self.store = Store(self.root)
        ensure_demo(self.root / "datasets")
        self.setWindowTitle("AStock · 量化研究与仿真工作台")
        self.resize(1480, 940)
        self.setMinimumSize(820, 420)
        self.setDockNestingEnabled(True)
        self.theme_name = self.store.setting("theme", "dark")
        self.active_id = None
        self.workspace_run_ids = {1: None, 2: None}
        self.pending_run_mode = None
        self.states = {}
        self.quotes = {}
        self.datasets = []
        self.parameters = {}
        self.backtest_options = {}
        self.current_template = "双均线趋势"
        self.connected = False
        self.market_metrics = {"status": "未连接"}
        self.closing = False
        self.start_pending = False
        self.live_rule_token = None
        self.live_rule_request = None
        self.step_after_start = False
        self.worker_enabled = start_workers
        self.ctx = mp.get_context("spawn")
        self.engine_commands = self.ctx.Queue()
        self.market_commands = self.ctx.Queue()
        self.output = self.ctx.Queue()
        self._ipc_queues = (self.engine_commands, self.market_commands, self.output)
        self.processes = []
        self.history_process = None
        self.data_jobs = DataJobs(self.root / "datasets", self)
        self.data_jobs.message.connect(self.data_job_message)
        self.operations = {}
        self.preview_token = self.import_token = None
        self.trade_token = None
        self.trade_context = None
        self.preview_identity = None
        self.lesson_index = 0
        self.completed = set(self.store.setting("lessons_completed", []))
        self.learning_layout = None
        self.analysis_layout = None
        self._build_main()
        self._build_library()
        self._build_parameters()
        self._build_bottom()
        self._build_menu()
        from astock.learning_guide import LearningGuide
        self.learning = LearningGuide(self)
        self.statusBar().showMessage("就绪 · 数据与虚拟账户保存在本机")
        self.cancel_import_button = help_target(button("取消数据导入", self.cancel_import), 'window.MainWindow.__init__.cancel_import_button')
        self.cancel_import_button.hide()
        self.statusBar().addPermanentWidget(self.cancel_import_button)
        self.status_text = label("引擎未启动", "muted")
        self.statusBar().addPermanentWidget(self.status_text)
        self.account_status = label("虚拟账户：未运行", "muted")
        self.market_badge = label("行情：未连接", "muted")
        self.statusBar().addPermanentWidget(self.account_status)
        self.statusBar().addPermanentWidget(self.market_badge)
        self.load_template("双均线趋势", save_current=False)
        self.refresh_library()
        self.apply_theme()
        saved = self.store.setting("layout")
        if saved:
            self.restoreState(QtCore.QByteArray.fromBase64(saved.encode()))
        self.resizeDocks([self.library_dock, self.parameter_dock], [220, 290], QtCore.Qt.Orientation.Horizontal)
        self.resizeDocks([self.bottom_dock], [225], QtCore.Qt.Orientation.Vertical)
        self._select_demo("bar")
        self.show_lesson(0)
        self.install_research_shell()
        self.switch_workspace(0)
        if start_workers:
            self.processes = [
                self.ctx.Process(target=engine_worker, args=(self.engine_commands, self.output, str(self.root)), name="AStockEngine"),
                self.ctx.Process(target=market_worker, args=(self.market_commands, self.engine_commands, self.output, str(self.root)), name="AStockMarket"),
            ]
            for p in self.processes:
                p.start()
        self.poll_timer = QtCore.QTimer(self)
        self.poll_timer.timeout.connect(self.poll)
        self.poll_timer.start(80)
        self.freshness_timer = QtCore.QTimer(self)
        self.freshness_timer.timeout.connect(self.refresh_market_status)
        self.freshness_timer.start(1000)

    def fit_initial_layout(self, width, height):
        """Keep the workspace reachable on smaller screens at 125%/150% scaling."""
        compact = False
        if width < 1180:
            self.library_dock.hide()
            self.parameter_dock.hide()
            compact = True
        if height < 740:
            self.bottom_dock.hide()
            compact = True
        if height < 600 and self.workspace_scroll is None:
            central = self.takeCentralWidget()
            self.workspace_scroll = QtWidgets.QScrollArea()
            self.workspace_scroll.setWidgetResizable(True)
            self.workspace_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            self.workspace_scroll.setWidget(central)
            self.setCentralWidget(self.workspace_scroll)
        self.resize(width, height)
        if compact:
            self.statusBar().showMessage("紧凑布局 · 可通过「视图」菜单打开策略、参数及账户面板")

    def _build_main(self):
        central = QtWidgets.QWidget()
        central.setObjectName("workspace")
        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)
        self.nav_group = QtWidgets.QButtonGroup(self)
        rail = QtWidgets.QToolBar("主导航", self)
        rail.setObjectName("mainNavigationRail")
        rail.setMovable(False)
        rail.setFloatable(False)
        rail.setOrientation(QtCore.Qt.Orientation.Vertical)
        self.navigation_rail = rail
        self.addToolBar(QtCore.Qt.ToolBarArea.LeftToolBarArea, rail)
        brand = label("AStock", "brand")
        brand.setContentsMargins(10, 12, 10, 12)
        rail.addWidget(brand)
        for i, text in ((0, "写策略"), (1, "历史回测"), (2, "模拟交易"),
                        (5, "数据中心"), (4, "账户与记录"), (3, "量化课程")):
            nav = help_target(button(text), 'window.MainWindow._build_main.nav')
            nav.setObjectName("nav")
            nav.setCheckable(True)
            self.nav_group.addButton(nav, i)
            nav.setMinimumSize(116, 46)
            rail.addWidget(nav)
        self.nav_group.idClicked.connect(lambda index: self.open_course_library()
                                        if index == 3 else self.switch_workspace(index))
        self.mode_badge = label("虚拟资金", "badge")
        self.mode_badge.setContentsMargins(10, 12, 10, 12)
        rail.addWidget(self.mode_badge)
        self.notice = QtWidgets.QFrame()
        self.notice.setObjectName("panel")
        notice_layout = QtWidgets.QHBoxLayout(self.notice)
        self.notice_text = label("", "muted", True)
        notice_layout.addWidget(self.notice_text, 1)
        notice_layout.addWidget(help_target(button("查看日志", lambda: (self.bottom_dock.show(), self.bottom_tabs.setCurrentIndex(3))), 'window.MainWindow._build_main.button'))
        notice_layout.addWidget(help_target(button("关闭", self.notice.hide), 'window.MainWindow._build_main.button2'))
        outer.addWidget(self.notice)
        self.notice.hide()
        toolbar = QtWidgets.QToolBar()
        self.run_toolbar = toolbar
        toolbar.setMovable(False)
        self.mode_combo = help_target(QtWidgets.QComboBox(toolbar), 'window.MainWindow._build_main.mode_combo')
        self.mode_combo.addItem("历史 K 线回测", "backtest")
        self.mode_combo.addItem("快照录制回放", "replay")
        self.mode_combo.addItem("真实行情仿真", "live")
        self.mode_combo.setMinimumWidth(140)
        # The workspace and selected dataset determine the execution mode.
        self.mode_combo.hide()
        self.start_button = help_target(button("▶  开始运行", self.start_run, True), 'window.MainWindow._build_main.start_button')
        self.start_button.setParent(toolbar)
        self.start_button.setToolTip("创建新的独立虚拟账户；当前参数与源码一起保存")
        # Main start lives in the historical page; this legacy handle remains for automation.
        self.start_button.hide()
        self.pause_action = help_target(toolbar.addAction("暂停", lambda: self.send_run("pause")), 'window.MainWindow._build_main.pause_action')
        self.resume_action = help_target(toolbar.addAction("继续", lambda: self.send_run("resume")), 'window.MainWindow._build_main.resume_action')
        self.pause_action.setEnabled(False)
        self.resume_action.setEnabled(False)
        self.step_action = help_target(toolbar.addAction("下一时刻", self.step_run), 'window.MainWindow._build_main.step_action')
        self.step_action.setToolTip("单步推进一个行情时刻，同一时刻的多个证券一起处理，不代表一笔交易。")
        self.mode_combo.currentIndexChanged.connect(lambda: self.step_action.setEnabled(
            self.mode_combo.currentData() in ("backtest", "replay")))
        self.speed_combo = help_target(QtWidgets.QComboBox(), 'window.MainWindow._build_main.speed_combo')
        toolbar.addWidget(label('快照回放速度'))
        self.speed_combo.setAccessibleName('快照回放速度')
        for x in (1, 5, 20, 100, 1000):
            self.speed_combo.addItem(f"{x}×", x)
        self.speed_combo.setCurrentIndex(2)
        self.speed_combo.currentIndexChanged.connect(self.change_replay_speed)
        toolbar.addWidget(self.speed_combo)
        stop = help_target(button("停止并撤单", lambda: self.send_run("stop")), 'window.MainWindow._build_main.stop')
        self.stop_button = stop
        stop.setEnabled(False)
        stop.setObjectName("danger")
        toolbar.addWidget(stop)
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setMaximumWidth(130)
        self.progress.setValue(0)
        self.progress.setFormat("就绪")
        toolbar.addWidget(self.progress)
        outer.addWidget(toolbar)
        toolbar.hide()
        self.guide_strip = QtWidgets.QFrame()
        self.guide_strip.setObjectName("panel")
        guide_layout = QtWidgets.QHBoxLayout(self.guide_strip)
        guide_layout.setContentsMargins(10, 6, 10, 6)
        self.guide_text = label("", "muted", True)
        self.guide_text.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        guide_layout.addWidget(self.guide_text, 1)
        self.guide_next = help_target(button("下一步", lambda: self.learning.act(), True), 'window.MainWindow._build_main.guide_next')
        guide_layout.addWidget(self.guide_next)
        guide_layout.addWidget(help_target(button("使用教程", self.replay_usage_tutorial), 'window.MainWindow._build_main.button3'))
        guide_layout.addWidget(help_target(button("收起", self.guide_strip.hide), 'window.MainWindow._build_main.button4'))
        outer.addWidget(self.guide_strip)
        self.guide_strip.hide()
        self.metrics_panel = QtWidgets.QWidget()
        metrics = QtWidgets.QHBoxLayout(self.metrics_panel)
        metrics.setContentsMargins(0, 0, 0, 0)
        self.metric_values = {}
        for key, title, initial in (("equity", "账户总权益", "100,000.00"), ("return", "累计收益", "—"),
                                    ("drawdown", "最大回撤", "—"), ("fees", "累计费用", "0.00")):
            box = QtWidgets.QFrame()
            box.setObjectName("metric")
            inner = QtWidgets.QHBoxLayout(box)
            inner.setContentsMargins(6, 3, 6, 3)
            inner.addWidget(label(title, "muted"))
            value = label(initial, "metricValue")
            inner.addWidget(value)
            self.metric_values[key] = value
            metrics.addWidget(box)
        outer.addWidget(self.metrics_panel)
        self.pages = WorkspaceStack()
        self.workspace_scroll = QtWidgets.QScrollArea()
        self.workspace_scroll.setWidgetResizable(True)
        self.workspace_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.workspace_scroll.setWidget(self.pages)
        outer.addWidget(self.workspace_scroll, 1)
        self._research_page()
        self._backtest_page()
        self._live_page()
        self._learning_page()
        from astock.qmt_workspace import build_home, build_market
        build_home(self)
        build_market(self)
        # Dock resizing can leave less space than a chart's usable minimum even
        # on a large screen. Let the workspace scroll instead of overlapping it.
        self.setCentralWidget(central)

    def _research_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QtWidgets.QHBoxLayout()
        self.strategy_title = label("双均线趋势", "title")
        top.addWidget(self.strategy_title)
        top.addStretch()
        layout.addLayout(top)
        self.strategy_description = label("", "muted", True)
        layout.addWidget(self.strategy_description)
        from astock.qmt_workspace import name_model, export_model
        model_actions = QtWidgets.QHBoxLayout()
        model_actions.addWidget(help_target(button("另存副本", lambda: name_model(self)), 'window.MainWindow._research_page.button'))
        model_actions.addWidget(help_target(button("导出源码", lambda: export_model(self)), 'window.MainWindow._research_page.button2'))
        model_actions.addStretch()
        layout.addLayout(model_actions)
        split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.editor = help_target(CodeEditor(), 'window.MainWindow._research_page.editor')
        split.addWidget(self.editor)
        preview = QtWidgets.QWidget()
        self.research_preview = preview
        preview_layout = QtWidgets.QVBoxLayout(preview)
        preview_layout.setContentsMargins(8, 0, 0, 0)
        self.preview_chart = help_target(PriceChart("数据预览"), 'window.MainWindow._research_page.preview_chart')
        preview_layout.addWidget(self.preview_chart, 1)
        self.data_badge = label("教学数据 · 合成行情", "badge", True)
        preview_layout.addWidget(self.data_badge)
        self.cancel_preview_button = help_target(button("取消预览加载", self.cancel_preview), 'window.MainWindow._research_page.cancel_preview_button')
        self.cancel_preview_button.hide()
        preview_layout.addWidget(self.cancel_preview_button)
        self.research_hint = label("从右侧调整参数，然后运行回测。点击底部成交记录，可追溯策略判断。", "muted", True)
        preview_layout.addWidget(self.research_hint)
        split.addWidget(preview)
        split.setSizes([550, 350])
        layout.addWidget(split, 1)
        self.pages.addWidget(page)

    def _backtest_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(label("历史回测", "title"))
        top.addStretch()
        self.backtest_choose_button = help_target(button("选择策略", self.choose_backtest_strategy), 'window.MainWindow._backtest_page.backtest_choose_button')
        self.backtest_settings_button = help_target(button("回测设置", self.configure_backtest), 'window.MainWindow._backtest_page.button')
        self.backtest_start_button = help_target(button("开始回测", self.start_historical, True), 'window.MainWindow._backtest_page.button7')
        for control in (self.backtest_choose_button, self.backtest_settings_button, self.backtest_start_button):
            top.addWidget(control)
        layout.addLayout(top)
        self.backtest_strategy_label = label("", "muted", True)
        self.backtest_strategy_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.backtest_strategy_label)
        layout.addWidget(label("本页运行历史数据实验。已保存运行、报告导出和多次对比统一到「账户与记录」。", "muted", True))
        self.backtest_controls_toggle = help_target(QtWidgets.QCheckBox("展开运行控制（暂停 / 单步 / 速度）"), 'window.MainWindow._backtest_page.backtest_controls_toggle')
        self.backtest_controls_toggle.toggled.connect(self.refresh_execution_controls)
        layout.addWidget(self.backtest_controls_toggle)
        # Kept as a private layout hook for existing integrations, not another primary button.
        self.analysis_expand = help_target(button("展开分析", self.toggle_analysis_layout), 'window.MainWindow._backtest_page.analysis_expand')
        self.analysis_expand.setParent(page)
        self.analysis_expand.hide()
        self.result_description = label("先运行一次回测。策略权益、价格基准和回撤会在这里同步显示。", "muted", True)
        layout.addWidget(self.result_description)
        self.backtest_range = label("请选择历史数据；这里将显示实际起止时间。", "muted", True)
        self.backtest_range.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        details = QtWidgets.QWidget()
        details_layout = QtWidgets.QVBoxLayout(details)
        details_layout.setContentsMargins(4, 0, 4, 0)
        details_layout.addWidget(self.backtest_range)
        self.backtest_progress = label("先打开「回测设置」核对日期、资金和基准。开始运行自动完成；下一时刻用于单步调试。", "muted", True)
        details_layout.addWidget(self.backtest_progress)
        details_toggle = help_target(QtWidgets.QCheckBox("显示数据范围与运行进度"), 'window.MainWindow._backtest_page.details_toggle')
        details_toggle.toggled.connect(details.setVisible)
        layout.addWidget(details_toggle)
        layout.addWidget(details)
        details.hide()
        self.result_tabs = help_target(QtWidgets.QTabWidget(), 'window.MainWindow._backtest_page.result_tabs')
        self.equity_chart = help_target(EquityChart(), 'window.MainWindow._backtest_page.equity_chart')
        self.result_tabs.addTab(self.equity_chart, "净值与回撤")
        trade_page = QtWidgets.QWidget()
        trade_layout = QtWidgets.QVBoxLayout(trade_page)
        self.chart_symbol = help_target(QtWidgets.QComboBox(), 'window.MainWindow._backtest_page.chart_symbol')
        self.chart_symbol.currentTextChanged.connect(self.refresh_result_chart)
        chart_toolbar = QtWidgets.QHBoxLayout()
        chart_toolbar.addWidget(self.chart_symbol, 1)
        chart_toolbar.addWidget(help_target(button("返回最新行情", self.clear_trade_context), 'window.MainWindow._backtest_page.button8'))
        trade_layout.addLayout(chart_toolbar)
        self.result_chart = help_target(PriceChart(), 'window.MainWindow._backtest_page.result_chart')
        # The detail tab also contains a selector and explanation. Its chart
        # must be allowed to shrink without overlapping these sibling widgets.
        self.result_chart.setMinimumHeight(110)
        self.result_chart.volume.setMaximumHeight(48)
        trade_layout.addWidget(self.result_chart, 1)
        self.trade_explanation = label("选择下方成交记录，定位图上买卖点并显示原因。", "muted", True)
        trade_layout.addWidget(self.trade_explanation)
        self.result_tabs.addTab(trade_page, "价格与买卖点")
        self.trade_page = trade_page
        self.manifest_text = help_target(QtWidgets.QTextBrowser(), 'window.MainWindow._backtest_page.manifest_text')
        self.result_tabs.addTab(self.manifest_text, "运行依据")
        activity = QtWidgets.QWidget()
        activity_layout = QtWidgets.QVBoxLayout(activity)
        activity_layout.addWidget(label("委托是下单请求，成交才是实际买卖。点击成交可定位图表；日志记录策略判断及拒单原因。", "muted", True))
        self.activity_tabs = help_target(QtWidgets.QTabWidget(), 'window.MainWindow._backtest_page.activity_tabs')
        self.activity_orders = help_target(RecordTable(
            ["下单时间", "订单", "证券", "方向", "委托量", "成交量", "限价", "状态", "下单理由 / 状态说明"],
            lambda o: [o.created.strftime("%Y-%m-%d %H:%M:%S"), o.id, o.symbol,
                       "买" if o.side == "BUY" else "卖", o.quantity, o.filled, str(o.price),
                       STATUS[o.status], o.reason + " / " + o.note], [170, 88, 110, 50, 70, 70, 80, 85]), 'window.MainWindow._backtest_page.activity_orders')
        self.activity_trades = help_target(RecordTable(
            ["成交时间", "成交", "对应订单", "证券", "方向", "数量", "价格", "费用", "策略理由"],
            lambda t: [t.time.strftime("%Y-%m-%d %H:%M:%S"), t.id, t.order_id, t.symbol,
                       "买" if t.side == "BUY" else "卖", t.quantity, str(t.price), f"{t.fee:.2f}", t.reason],
            [170, 88, 88, 110, 50, 70, 80, 75]), 'window.MainWindow._backtest_page.activity_trades')
        self.activity_trades.itemSelectionChanged.connect(lambda: self.select_trade(self.activity_trades))
        self.activity_logs = help_target(QtWidgets.QPlainTextEdit(), 'window.MainWindow._backtest_page.activity_logs')
        self.activity_logs.setReadOnly(True)
        self.activity_logs.setMaximumBlockCount(1000)
        for widget, title in ((self.activity_orders, "下单与状态"), (self.activity_trades, "成交明细"),
                              (self.activity_logs, "策略日志")):
            self.activity_tabs.addTab(widget, title)
        activity_layout.addWidget(self.activity_tabs)
        self.result_tabs.addTab(activity, "操作记录")
        self.diagnostics = help_target(QtWidgets.QTextBrowser(), 'window.MainWindow._backtest_page.diagnostics')
        from astock.backtest_analysis import diagnostics_html
        self.diagnostics.setHtml(diagnostics_html([], 100000))
        self.result_tabs.addTab(self.diagnostics, "回测诊断 / 分月表现")
        from astock.backtest_workspace import build_overview
        self.backtest_overview = build_overview(self)
        self.result_tabs.insertTab(0, self.backtest_overview, "回测总览")
        self.result_tabs.setCurrentIndex(0)
        self.result_tabs.currentChanged.connect(self.refresh_diagnostics)
        layout.addWidget(self.result_tabs, 1)
        self.pages.addWidget(page)

    def _live_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(label("模拟交易 · 本地虚拟资金", "title"))
        top.addStretch()
        self.connect_button = help_target(button("连接行情", self.toggle_market, True), 'window.MainWindow._live_page.connect_button')
        top.addWidget(self.connect_button)
        self.record_check = help_target(QtWidgets.QCheckBox("录制行情"), 'window.MainWindow._live_page.record_check')
        self.record_check.toggled.connect(lambda enabled: self.market_commands.put({"op": "record", "enabled": enabled}))
        top.addWidget(self.record_check)
        top.addWidget(help_target(button("启动策略仿真", lambda: self.start_live(False)), 'window.MainWindow._live_page.button'))
        layout.addLayout(top)
        self.market_status = label("尚未连接 · 免费报价目标每 5 秒一轮 · 快照近似仿真", "muted", True)
        layout.addWidget(self.market_status)
        rule_row = QtWidgets.QHBoxLayout()
        self.live_rule_status = label("ETF 账户创建前会核对当日资料；跨日需更新后继续。", "muted", True)
        rule_row.addWidget(self.live_rule_status, 1)
        self.refresh_live_rule_button = help_target(button("更新当日规则", self.refresh_active_live_rules), 'window.MainWindow._live_page.refresh_live_rule_button')
        self.cancel_live_rule_button = help_target(button("取消准备", self.cancel_live_rule_preparation), 'window.MainWindow._live_page.cancel_live_rule_button')
        self.cancel_live_rule_button.hide()
        rule_row.addWidget(self.refresh_live_rule_button)
        rule_row.addWidget(self.cancel_live_rule_button)
        layout.addLayout(rule_row)
        self.quote_table = help_target(table(["代码 / 名称", "最新", "买一", "卖一", "行情时间", "年龄 / 秒"]), 'window.MainWindow._live_page.quote_table')
        self.quote_table.setMinimumHeight(100)
        self.live_tabs = help_target(QtWidgets.QTabWidget(), 'window.MainWindow._live_page.live_tabs')
        from astock.model_trading import TradingTasks
        self.trading_tasks = TradingTasks(self)
        self.live_tabs.addTab(self.trading_tasks, "策略交易")
        self.live_tabs.addTab(self.quote_table, "行情快照")
        self.live_manifest_text = help_target(QtWidgets.QTextBrowser(), 'window.MainWindow._live_page.live_manifest_text')
        self.live_tabs.addTab(self.live_manifest_text, "账户规则与依据")
        self.trading_control_bar = QtWidgets.QWidget()
        controls = QtWidgets.QHBoxLayout(self.trading_control_bar)
        self.trading_pause_button = help_target(button("暂停", lambda: self.send_run("pause")), 'window.MainWindow._live_page.trading_pause_button')
        self.trading_resume_button = help_target(button("继续", lambda: self.send_run("resume")), 'window.MainWindow._live_page.trading_resume_button')
        self.trading_stop_button = help_target(button("停止并撤单", lambda: self.send_run("stop")), 'window.MainWindow._live_page.trading_stop_button')
        for control in (self.trading_pause_button, self.trading_resume_button, self.trading_stop_button):
            controls.addWidget(control)
            control.setEnabled(False)
        controls.addStretch()
        layout.addWidget(self.trading_control_bar)
        layout.addWidget(self.live_tabs, 1)
        form_box = QtWidgets.QGroupBox("手动练习 · 独立虚拟账户")
        form = QtWidgets.QGridLayout(form_box)
        self.manual_symbol = help_target(QtWidgets.QLineEdit("510300.SH"), 'window.MainWindow._live_page.manual_symbol')
        self.manual_side = help_target(QtWidgets.QComboBox(), 'window.MainWindow._live_page.manual_side')
        self.manual_side.addItems(["买入", "卖出"])
        self.manual_qty = help_target(QtWidgets.QSpinBox(), 'window.MainWindow._live_page.manual_qty')
        self.manual_qty.setRange(1, 1000000)
        self.manual_qty.setSingleStep(100)
        self.manual_qty.setValue(100)
        self.manual_price = help_target(QtWidgets.QDoubleSpinBox(), 'window.MainWindow._live_page.manual_price')
        self.manual_price.setDecimals(3)
        self.manual_price.setRange(.001, 100000)
        self.manual_price.setValue(4)
        form.addWidget(label("证券"), 0, 0)
        form.addWidget(self.manual_symbol, 0, 1)
        form.addWidget(self.manual_side, 0, 2)
        form.addWidget(label("数量"), 0, 3)
        form.addWidget(self.manual_qty, 0, 4)
        form.addWidget(label("限价"), 0, 5)
        form.addWidget(self.manual_price, 0, 6)
        self.create_manual_button = help_target(button("建立练习账户", lambda: self.start_live(True)), 'window.MainWindow._live_page.create_manual_button')
        form.addWidget(self.create_manual_button, 1, 0, 1, 2)
        form.addWidget(help_target(button("取对手价", self.use_opposite_price), 'window.MainWindow._live_page.button2'), 1, 2, 1, 2)
        form.addWidget(help_target(button("提交模拟委托", self.manual_order), 'window.MainWindow._live_page.button3'), 1, 4, 1, 3)
        self.manual_form = form_box
        self.live_tabs.addTab(form_box, "普通交易 · 手动练习")
        layout.addWidget(label("模拟成交受价格、数量、T+1、流动性与行情新鲜度约束。盘后报价不触发交易。", "muted", True))
        self.pages.addWidget(page)

    def _learning_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(label("学习中心", "title"))
        top.addStretch()
        self.lesson_progress = label("0 / 4 已完成", "badge")
        top.addWidget(self.lesson_progress)
        self.lesson_reading = help_target(button("展开课程", self.toggle_learning_layout), 'window.MainWindow._learning_page.lesson_reading')
        top.addWidget(self.lesson_reading)
        top.addWidget(help_target(button("术语速查", self.show_glossary), 'window.MainWindow._learning_page.button'))
        layout.addLayout(top)
        tabs = QtWidgets.QHBoxLayout()
        self.lesson_buttons = []
        for i, lesson in enumerate(LESSONS):
            b = help_target(button(lesson["title"], lambda checked=False, n=i: self.show_lesson(n)), 'window.MainWindow._learning_page.b')
            b.setObjectName("lessonNav")
            self.lesson_buttons.append(b)
            tabs.addWidget(b)
        layout.addLayout(tabs)
        self.lesson_body = help_target(QtWidgets.QTextBrowser(), 'window.MainWindow._learning_page.lesson_body')
        self.lesson_body.setOpenExternalLinks(True)
        layout.addWidget(self.lesson_body, 1)
        self.lesson_steps = label("", "muted", True)
        self.lesson_steps.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        layout.addWidget(self.lesson_steps)
        actions = QtWidgets.QHBoxLayout()
        self.lesson_goal = label("", "muted", True)
        actions.addWidget(self.lesson_goal, 1)
        self.lesson_action = help_target(button("开始练习", self.lesson_do, True), 'window.MainWindow._learning_page.lesson_action')
        actions.addWidget(self.lesson_action)
        self.lesson_done_button = help_target(button("标记本节已读", self.complete_lesson), 'window.MainWindow._learning_page.lesson_done_button')
        actions.addWidget(self.lesson_done_button)
        layout.addLayout(actions)
        self.lesson_offline = help_target(button("无网络 / 休市：离线演练", lambda: self.learning.begin(3, offline=True)), 'window.MainWindow._learning_page.lesson_offline')
        layout.addWidget(self.lesson_offline)
        self.lesson_resume_guide = help_target(button("显示当前练习提示", lambda: (self.guide_strip.show(), self.learning.render())), 'window.MainWindow._learning_page.lesson_resume_guide')
        layout.addWidget(self.lesson_resume_guide)
        self.equity_lesson_button = help_target(button("载入分红与送转练习（离线）", self.prepare_equity_lesson), 'window.MainWindow._learning_page.equity_lesson_button')
        layout.addWidget(self.equity_lesson_button)
        self.learning_sections = help_target(QtWidgets.QTabWidget(), 'window.MainWindow._learning_page.learning_sections')
        self.learning_sections.addTab(page, "入门实作 · 引擎验证")
        from astock.qmt_workspace import MigrationCourse
        self.migration_course = MigrationCourse(self)
        self.learning_sections.addTab(self.migration_course, "QMT 迁移 · 八课自测")
        from astock.course_ui import CourseLibrary
        self.course_library = CourseLibrary(self)
        self.learning_sections.addTab(self.course_library, "操作手册与长期课程")
        self.learning_sections.setCurrentWidget(self.course_library)
        # Legacy exercises remain internal for compatibility, not a second course system.
        self.learning_sections.tabBar().hide()
        learning_page = QtWidgets.QWidget()
        learning_layout = QtWidgets.QVBoxLayout(learning_page)
        learning_layout.setContentsMargins(0, 0, 0, 0)
        learning_layout.addWidget(self.learning_sections)
        self.pages.addWidget(learning_page)

    def _dock(self, title, name, widget, area):
        dock = QtWidgets.QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        title_bar = QtWidgets.QWidget()
        title_bar.setObjectName("sidepanel")
        title_layout = QtWidgets.QHBoxLayout(title_bar)
        title_layout.setContentsMargins(9, 4, 5, 4)
        title_layout.addWidget(label(title), 1)
        detach = help_target(QtWidgets.QToolButton(), 'window.MainWindow._dock.detach')
        detach.setText("↗")
        detach.setToolTip("浮动 / 停靠面板；拖动标题栏调整位置")
        detach.setAccessibleName(title + "浮动或停靠")
        detach.clicked.connect(lambda: dock.setFloating(not dock.isFloating()))
        close = help_target(QtWidgets.QToolButton(), 'window.MainWindow._dock.close')
        close.setText("×")
        close.setToolTip("收起面板，可从「视图」菜单重新打开")
        close.setAccessibleName(title + "收起")
        close.clicked.connect(dock.hide)
        title_layout.addWidget(detach)
        title_layout.addWidget(close)
        dock.setTitleBarWidget(title_bar)
        self.addDockWidget(area, dock)
        return dock

    def _build_library(self):
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        self.library = help_target(QtWidgets.QTreeWidget(), 'window.MainWindow._build_library.library')
        self.library.setHeaderHidden(True)
        self.library.itemClicked.connect(self.library_clicked)
        layout.addWidget(self.library, 1)
        layout.addWidget(help_target(button("数据中心", self.open_data_center), 'window.MainWindow._build_library.button'))
        layout.addWidget(help_target(button("证券目录 / 搜索", self.open_catalog), 'window.MainWindow._build_library.button2'))
        layout.addWidget(help_target(button("打开本机数据目录", lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.root)))), 'window.MainWindow._build_library.button3'))
        self.library_dock = self._dock("研究资源", "library", panel, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        self.library_dock.setMinimumWidth(180)

    def _build_parameters(self):
        content = QtWidgets.QWidget()
        content.setObjectName("sidepanel")
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)
        layout.addWidget(label("数据与账户", "badge"))
        layout.addWidget(label("历史 / 回放数据集", "muted"))
        self.dataset_combo = help_target(QtWidgets.QComboBox(), 'window.MainWindow._build_parameters.dataset_combo')
        self.dataset_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.dataset_combo.setMinimumContentsLength(18)
        self.dataset_combo.currentIndexChanged.connect(self.dataset_changed)
        layout.addWidget(self.dataset_combo)
        self.online_symbols_panel = QtWidgets.QWidget()
        online_layout = QtWidgets.QVBoxLayout(self.online_symbols_panel)
        online_layout.setContentsMargins(0, 0, 0, 0)
        online_layout.addWidget(label("在线标的（用逗号分隔）", "muted"))
        self.symbol_input = help_target(QtWidgets.QLineEdit(self.store.setting("watchlist", "600000.SH,000001.SZ,510300.SH,159915.SZ")), 'window.MainWindow._build_parameters.symbol_input')
        self.symbol_input.setCursorPosition(0)
        self.symbol_input.setToolTip("最多 20 个沪深 A 股或场内 ETF；例如 600000.SH,510300.SH")
        online_layout.addWidget(self.symbol_input)
        online_layout.addWidget(help_target(button("按名称 / 代码添加", self.open_catalog), 'window.MainWindow._build_parameters.button'))
        layout.addWidget(self.online_symbols_panel)
        self.mode_combo.currentIndexChanged.connect(self.refresh_context_controls)
        layout.addWidget(label("初始虚拟资金 / 元", "muted"))
        self.capital = help_target(QtWidgets.QDoubleSpinBox(), 'window.MainWindow._build_parameters.capital')
        self.capital.setRange(*INITIAL_CAPITAL_RANGE)
        self.capital.setDecimals(2)
        self.capital.setValue(100000)
        self.capital.setSingleStep(10000)
        layout.addWidget(self.capital)
        layout.addWidget(label("策略参数", "badge"))
        self.param_widget = QtWidgets.QWidget()
        self.param_form = QtWidgets.QFormLayout(self.param_widget)
        self.param_form.setContentsMargins(0, 0, 0, 0)
        self.param_form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapAllRows)
        layout.addWidget(self.param_widget)
        fee_group = QtWidgets.QGroupBox("撮合与额度设置")
        fees = QtWidgets.QFormLayout(fee_group)
        fees.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapAllRows)
        self.commission = help_target(QtWidgets.QDoubleSpinBox(), 'window.MainWindow._build_parameters.commission')
        self.commission.setRange(0, 100)
        self.commission.setDecimals(2)
        self.commission.setValue(3)
        fees.addRow("佣金 / 万分之", self.commission)
        self.minimum_fee = help_target(QtWidgets.QDoubleSpinBox(), 'window.MainWindow._build_parameters.minimum_fee')
        self.minimum_fee.setRange(0, 1000)
        self.minimum_fee.setValue(5)
        fees.addRow("单笔最低佣金 / 元", self.minimum_fee)
        self.participation = help_target(QtWidgets.QDoubleSpinBox(), 'window.MainWindow._build_parameters.participation')
        self.participation.setRange(.1, 100)
        self.participation.setValue(10)
        self.participation.setSuffix(" %")
        fees.addRow("成交量参与上限", self.participation)
        self.slippage = help_target(QtWidgets.QSpinBox(), 'window.MainWindow._build_parameters.slippage')
        self.slippage.setRange(0, 100)
        self.slippage.setValue(1)
        fees.addRow("不利滑点 / 价格单位", self.slippage)
        self.position_limit = help_target(QtWidgets.QDoubleSpinBox(), 'window.MainWindow._build_parameters.position_limit')
        self.position_limit.setRange(1, 100)
        self.position_limit.setValue(100)
        self.position_limit.setSuffix(" %")
        fees.addRow("单标的仓位上限", self.position_limit)
        self.order_limit = help_target(QtWidgets.QDoubleSpinBox(), 'window.MainWindow._build_parameters.order_limit')
        self.order_limit.setRange(100, 100000000)
        self.order_limit.setValue(100000)
        fees.addRow("单笔金额上限 / 元", self.order_limit)
        layout.addWidget(fee_group)
        self.help_panel = QtWidgets.QGroupBox("随手学")
        help_layout = QtWidgets.QVBoxLayout(self.help_panel)
        self.context_help = label("参数表单来自源码的 PARAMETERS。回测会保存代码与参数版本，方便复查。", "muted", True)
        help_layout.addWidget(self.context_help)
        help_layout.addWidget(help_target(button("查看量化课程", self.open_course_library), 'window.MainWindow._build_parameters.button2'))
        layout.addWidget(self.help_panel)
        layout.addStretch()
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        self.editor_settings = help_target(QtWidgets.QTabWidget(), 'window.MainWindow._build_parameters.editor_settings')
        self.editor_settings.setTabPosition(QtWidgets.QTabWidget.TabPosition.South)
        sections = []
        for title in ("基本信息", "参数设置", "回测参数", "操作指引"):
            section = QtWidgets.QWidget()
            section_layout = QtWidgets.QVBoxLayout(section)
            section_layout.setContentsMargins(4, 4, 4, 4)
            sections.append(section_layout)
            self.editor_settings.addTab(section, title)
        group = 0
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is None:
                continue
            if isinstance(widget, QtWidgets.QLabel) and widget.text() == "策略参数":
                group = 1
            if widget is fee_group:
                group = 2
            if widget is self.help_panel:
                group = 3
            sections[group].addWidget(widget)
        self.check_parameters_button = help_target(button("检查参数", self.rebuild_parameters), 'window.MainWindow._build_parameters.check_parameters_button')
        sections[1].insertWidget(1, self.check_parameters_button)
        sections[0].addWidget(help_target(button("补充历史数据", self.open_data_center), 'window.MainWindow._build_parameters.button3'))
        sections[2].insertWidget(0, help_target(button("设置回测区间 / 基准", self.configure_backtest), 'window.MainWindow._build_parameters.button4'))
        for section_layout in sections:
            section_layout.addStretch()
        layout.addWidget(self.editor_settings)
        scroll.setWidget(content)
        self.parameter_scroll = scroll
        self.parameter_dock = self._dock("参数与说明", "parameters", scroll, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        self.parameter_dock.setMinimumWidth(255)

    def _build_bottom(self):
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        line = QtWidgets.QHBoxLayout()
        self.account_label = label("账户：尚未创建  |  可用资金 —  |  冻结资金 —", "muted")
        line.addWidget(self.account_label, 1)
        line.addWidget(help_target(button("撤销选中委托", self.cancel_selected), 'window.MainWindow._build_bottom.button'))
        layout.addLayout(line)
        self.bottom_tabs = help_target(QtWidgets.QTabWidget(), 'window.MainWindow._build_bottom.bottom_tabs')
        self.positions_table = help_target(table(["证券", "持仓", "可卖", "成本金额", "最新价", "浮动盈亏"]), 'window.MainWindow._build_bottom.positions_table')
        self.orders_table = help_target(RecordTable(["订单", "证券", "方向", "委托数量", "已成交", "限价", "状态", "状态说明"],
            lambda o: [o.id, o.symbol, "买" if o.side == "BUY" else "卖", o.quantity, o.filled,
                       str(o.price), STATUS[o.status], o.note], [88, 110, 58, 85, 70, 80, 92]), 'window.MainWindow._build_bottom.orders_table')
        self.trades_table = help_target(RecordTable(["成交", "时间", "证券", "方向", "数量", "价格", "费用", "策略理由"],
            lambda t: [t.id, t.time.strftime("%m-%d %H:%M:%S"), t.symbol, "买" if t.side == "BUY" else "卖",
                       t.quantity, str(t.price), f"{t.fee:.2f}", t.reason], [88, 155, 110, 58, 75, 85, 80]), 'window.MainWindow._build_bottom.trades_table')
        self.trades_table.itemSelectionChanged.connect(self.select_trade)
        self.log_view = help_target(QtWidgets.QPlainTextEdit(), 'window.MainWindow._build_bottom.log_view')
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1000)
        for widget, title in ((self.positions_table, "持仓"), (self.orders_table, "委托"),
                              (self.trades_table, "成交"), (self.log_view, "解释与日志")):
            self.bottom_tabs.addTab(widget, title)
        equity_page = QtWidgets.QWidget()
        equity_layout = QtWidgets.QVBoxLayout(equity_page)
        equity_layout.setContentsMargins(6, 4, 6, 4)
        self.equity_note = label("运行后可查看分红登记、到账和份额变化。", "muted")
        self.equity_note.setWordWrap(True)
        equity_layout.addWidget(self.equity_note)
        self.equity_table = help_target(RecordTable(EQUITY_HEADERS, equity_row, [88, 170, 110, 90, 90, 90, 85, 105, 105]), 'window.MainWindow._build_bottom.equity_table')
        self.equity_table.setMinimumHeight(110)
        equity_layout.addWidget(self.equity_table, 1)
        self.bottom_tabs.addTab(equity_page, "权益流水")
        layout.addWidget(self.bottom_tabs, 1)
        self.bottom_dock = self._dock("账户与执行", "execution", panel, QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)

    def _build_menu(self):
        from astock.help_controller import HelpController
        self.help_controller = HelpController(self)
        file_menu = self.menuBar().addMenu("文件")
        for title, fn, shortcut in (("保存策略", self.save_strategy, "Ctrl+S"),
                                    ("导入 Python 策略", self.import_strategy, "Ctrl+O"),
                                    ("报告归档与导出", self.export_current, "Ctrl+E"),
                                    ("数据中心", self.open_data_center, "Ctrl+D")):
            a = help_target(file_menu.addAction(title), 'window.MainWindow._build_menu.a')
            a.triggered.connect(fn)
            a.setShortcut(shortcut)
        file_menu.addSeparator()
        help_target(file_menu.addAction("退出", self.close), 'window.MainWindow._build_menu.addAction')
        view = self.menuBar().addMenu("视图")
        view.setToolTipsVisible(True)
        for dock in (self.library_dock, self.parameter_dock, self.bottom_dock):
            view.addAction(dock.toggleViewAction())
        view.addSeparator()
        help_target(view.addAction("切换深色 / 浅色", self.toggle_theme), 'window.MainWindow._build_menu.addAction2')
        help_target(view.addAction("显示 / 隐藏教学提示", self.toggle_teaching_hints), 'window.MainWindow._build_menu.addAction3')
        help_target(view.addAction("恢复默认布局", self.reset_layout), 'window.MainWindow._build_menu.addAction4')
        help_menu = self.menuBar().addMenu("帮助")
        help_target(help_menu.addAction("使用教程重放", self.replay_usage_tutorial), 'window.MainWindow._build_menu.replay_tutorial')
        help_target(help_menu.addAction("初始化应用", self.request_initialization), 'window.MainWindow._build_menu.initialize_app')
        help_menu.addSeparator()
        help_target(help_menu.addAction("关于 AStock", lambda: QtWidgets.QMessageBox.information(
            self, "AStock", "个人量化研究与仿真工作台\n所有交易均使用本地虚拟资金。\n数据目录：" + str(self.root))), 'window.MainWindow._build_menu.addAction9')

    def replay_usage_tutorial(self, start_chapter=None):
        from astock.onboarding import open_onboarding
        return open_onboarding(self, start_chapter=start_chapter if isinstance(start_chapter, str) else None)

    def request_initialization(self):
        from astock.app_reset import confirm_initialization
        if confirm_initialization(self):
            self.reset_requested = True
            self.close()

    def open_course_library(self):
        self.learning_sections.setCurrentWidget(self.course_library)
        self.switch_workspace(3)

    def explain_current_page(self):
        from astock.control_help import ControlTour
        from shiboken6 import isValid
        if hasattr(self, 'control_tour') and isValid(self.control_tour):
            self.control_tour.close()
            self.control_tour.deleteLater()
        self.control_tour = ControlTour(self, QtWidgets.QApplication.activeWindow() or self)
        self.control_tour.show()

    def open_instruction_preview(self, kind):
        from astock.quality_ui import QualityDialog
        from astock.operations_ui import OperationDialog
        if kind == 'quality':
            dialog = QualityDialog(self.root, None, self, instruction_preview=True)
        else:
            dialog = OperationDialog(self.root, kind, parent=self, instruction_preview=True)
        # Keep native ownership; closing a preview cannot schedule a business job.
        dialog.show()
        from astock.control_help import ControlTour
        tour = ControlTour(self, dialog)
        tour.show()
        dialog.finished.connect(tour.close)
        dialog._instruction_tour = tour
        return dialog

    def open_task_guide(self):
        from astock.task_guide import TaskGuide
        if hasattr(self, 'task_guide'):
            self.task_guide.close()
            self.task_guide.deleteLater()
        self.task_guide = TaskGuide(self)
        self.task_guide.show()

    def reset_layout(self):
        for dock, area in ((self.library_dock, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea),
                           (self.parameter_dock, QtCore.Qt.DockWidgetArea.RightDockWidgetArea),
                           (self.bottom_dock, QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)):
            dock.setFloating(False)
            self.addDockWidget(area, dock)
        self.switch_workspace(self.pages.currentIndex())
        self.resizeDocks([self.library_dock, self.parameter_dock], [220, 290], QtCore.Qt.Orientation.Horizontal)
        self.resizeDocks([self.bottom_dock], [225], QtCore.Qt.Orientation.Vertical)
        self.strategy_dialog.split.setSizes([740, 330])

    def toggle_teaching_hints(self):
        if self.help_panel.isVisible():
            self.help_panel.hide()
            self.editor_settings.setCurrentIndex(1)
            if self.pages.currentIndex() not in (0, 2):
                self.parameter_dock.hide()
        else:
            self.help_panel.show()
            self.editor_settings.setCurrentIndex(3)
            if self.pages.currentIndex() != 0:
                self.parameter_dock.show()

    def open_practice(self):
        self.learning_sections.setCurrentIndex(0)
        self.switch_workspace(3)

    def install_research_shell(self):
        from astock.model_browser import ModelBrowser
        from astock.strategy_editor_window import StrategyEditorWindow
        research = self.pages.widget(0)
        self.pages.removeWidget(research)
        self.model_browser = ModelBrowser(self)
        self.strategy_library_dialog = QtWidgets.QDialog(self)
        self.strategy_library_dialog.setWindowTitle("模板与已存策略")
        self.strategy_library_dialog.resize(920, 600)
        library_layout = QtWidgets.QVBoxLayout(self.strategy_library_dialog)
        library_layout.addWidget(self.model_browser)
        self.strategy_dialog = StrategyEditorWindow(self, research)
        self.pages.insertWidget(0, self.strategy_dialog)
        self.new_strategy_button = self.strategy_dialog.new_button
        self.template_button = self.strategy_dialog.library_button
        self.save_strategy_button = self.strategy_dialog.save_button
        self.research_preview.hide()
        self.editor.textChanged.connect(self.refresh_backtest_strategy)

    def open_strategy_library(self):
        self.model_browser.refresh()
        self.strategy_library_dialog.show()
        self.strategy_library_dialog.raise_()

    def open_strategy_editor(self, kind=None, identity=None):
        if kind == "template":
            self.load_template(identity)
        elif kind == "saved":
            self.save_strategy(quiet=True)
            saved = next((s for s in self.store.strategies() if s["name"] == identity), None)
            if saved is None:
                self.error("模型已不存在，请刷新列表。")
                return False
            self.current_template = saved["name"]
            self.strategy_title.setText(saved["name"])
            self.editor.setPlainText(saved["code"])
            self.rebuild_parameters(values=saved["parameters"])
        self.switch_workspace(0)
        self.strategy_library_dialog.hide()
        self.strategy_dialog.open_editor()
        self.editor.setFocus()
        return True

    def switch_workspace(self, index):
        if index != 0 and hasattr(self, "strategy_dialog"):
            self.strategy_dialog.release_settings()
            self.strategy_library_dialog.hide()
        if index != 3 and self.learning_layout is not None:
            self.restore_learning_layout()
        if index != 1 and self.analysis_layout is not None:
            self.toggle_analysis_layout()
        changed = self.pages.currentIndex() != index
        self.pages.setCurrentIndex(index)
        if index == 4 and hasattr(self, "home_accounts"):
            self.home_accounts.refresh()
        if index == 5:
            from astock.qmt_workspace import refresh_data_overview
            self.refresh_library()
            refresh_data_overview(self)
        self.nav_group.button(index).setChecked(True)
        if hasattr(self, "backtest_strategy_label"):
            self.refresh_backtest_strategy()
        self.run_toolbar.setVisible(index == 1 and self.backtest_controls_toggle.isChecked())
        self.metrics_panel.setVisible(index not in (3, 4, 5))
        self.refresh_context_controls()
        if hasattr(self, "model_browser"):
            if index == 0:
                self.strategy_dialog.open_editor()
            # On this page the same controls already live beside the editor.
            # Opening their now-empty dock would create a misleading blank panel.
            self.parameter_dock.toggleViewAction().setEnabled(index != 0)
            self.parameter_dock.toggleViewAction().setToolTip(
                '参数已显示在写策略页面右侧，无需另开停靠面板。' if index == 0 else
                '显示或收起参数与撮合设置面板。')
            self.parameter_dock.setVisible(index == 2)
            self.library_dock.hide()
            self.bottom_dock.setVisible(index == 2)
            self.metrics_panel.setVisible(index == 2)
        if changed:
            self.workspace_scroll.verticalScrollBar().setValue(0)
            if index in (1, 2):
                candidate = self.states.get(self.active_id)
                allowed = ("backtest", "replay") if index == 1 else ("live", "manual")
                if self.workspace_run_ids[index] is None and candidate and candidate.get("mode") in allowed:
                    self.workspace_run_ids[index] = self.active_id
                self.active_id = self.workspace_run_ids[index]
                state = self.states.get(self.active_id)
                meta = next((m for m in self.datasets if m['id'] == self.dataset_combo.currentData()), {})
                mode = (state.get('mode') if state else None) or ('replay' if meta.get('kind') == 'quote' else 'backtest')
                self.mode_combo.setCurrentIndex(self.mode_combo.findData(mode if index == 1 else 'live'))
                if state and state.get("mode") in allowed:
                    self.display_run(state)
                else:
                    self.clear_execution_tables()
            self.refresh_execution_controls()

    def refresh_backtest_strategy(self, *_):
        if not hasattr(self, "parameters") or not hasattr(self, "editor"):
            return
        import hashlib
        code = self.editor.toPlainText()
        parameters = self.parameter_values()
        self.backtest_plan = {"name": self.current_template, "code": code, "parameters": parameters}
        saved = next((item for item in self.store.strategies() if item['name'] == self.current_template), None)
        status = "已保存" if saved and saved['code'] == code and saved['parameters'] == parameters else "当前编辑草稿"
        digest = hashlib.sha256(code.encode('utf-8')).hexdigest()[:8]
        values = "，".join(f"{name}={value}" for name, value in parameters.items()) or "无自定义参数"
        state = self.states.get(self.workspace_run_ids[1], {})
        manifest = state.get('manifest', {})
        matches = (manifest.get('name') == self.current_template and manifest.get('code') == code
                   and manifest.get('parameters') == parameters)
        result_status = '当前结果使用此配置' if matches else '尚未运行此配置'
        self.backtest_strategy_label.setText(f"待运行策略：{self.current_template} · {status} · {result_status} · 源码 {digest}\n参数：{values}")
        self.backtest_strategy_label.setToolTip("开始回测会使用这里所指的当前编辑源码与参数。下方当前结果属于已经创建的独立运行，不会被新草稿改写。")
        meta = next((m for m in self.datasets if m['id'] == self.dataset_combo.currentData()), {})
        self.backtest_start_button.setText('开始回放' if meta.get('kind') == 'quote' else
                                          '开始指数研究' if is_index(meta) else '开始回测')
        self.backtest_start_button.setToolTip('运行策略观察指数信号；指数本体委托会被拒绝，交易请使用对应股票或 ETF。'
                                              if is_index(meta) else '使用当前策略、参数和数据创建新的独立历史运行。')
        self.backtest_settings_button.setEnabled(True)
        self.backtest_settings_button.setToolTip('选择数据、设置初始资金；K 线支持日期区间和收益基准，快照回放使用完整录制区间。')

    def go_backtest(self):
        self.refresh_backtest_strategy()
        self.switch_workspace(1)

    def choose_backtest_strategy(self):
        choices = [("当前编辑草稿 · " + self.current_template, None, None)]
        choices.extend(("模板 · " + name, "template", name) for name in TEMPLATES)
        choices.extend(("已保存 · " + item['name'], "saved", item['name']) for item in self.store.strategies())
        selected, accepted = QtWidgets.QInputDialog.getItem(self, "选择回测策略", "下次回测使用的策略", [c[0] for c in choices], 0, False)
        if accepted:
            _, kind, identity = next(c for c in choices if c[0] == selected)
            if kind:
                self.open_strategy_editor(kind, identity)
            self.go_backtest()

    def refresh_execution_controls(self, *_):
        if not hasattr(self, 'pages') or not hasattr(self, 'backtest_controls_toggle'):
            return
        page = self.pages.currentIndex()
        self.run_toolbar.setVisible(page == 1 and self.backtest_controls_toggle.isChecked())
        self.start_button.hide()
        self.backtest_start_button.setEnabled(not self.start_pending)
        state = self.states.get(self.active_id)
        mode = state.get('mode') if state else None
        status = state.get('status') if state else None
        historical = mode in ('backtest', 'replay') and page == 1
        live = mode in ('live', 'manual') and page == 2
        self.pause_action.setEnabled(historical and status == 'RUNNING')
        self.resume_action.setEnabled(historical and status == 'PAUSED')
        self.step_action.setEnabled(historical and status in ('RUNNING', 'PAUSED') and not self.start_pending)
        self.stop_button.setEnabled(historical and status in ('RUNNING', 'PAUSED'))
        self.refresh_replay_speed()
        for control, enabled in ((self.trading_pause_button, live and status == 'RUNNING'),
                                 (self.trading_resume_button, live and status == 'PAUSED'),
                                 (self.trading_stop_button, live and status in ('RUNNING', 'PAUSED'))):
            control.setEnabled(enabled)

    def refresh_replay_speed(self):
        state = self.states.get(self.active_id)
        controlling = (self.pages.currentIndex() == 1 and state and
                       state.get('mode') in ('backtest', 'replay') and
                       state.get('status') in ('RUNNING', 'PAUSED'))
        meta = next((m for m in self.datasets if m['id'] == self.dataset_combo.currentData()), {})
        mode = state['mode'] if controlling else ('replay' if meta.get('kind') == 'quote' else 'backtest')
        enabled = self.pages.currentIndex() == 1 and mode == 'replay' and not self.start_pending
        self.speed_combo.setEnabled(enabled)
        if controlling and mode == 'replay' and 'speed' in state:
            index = self.speed_combo.findData(state['speed'])
            if index >= 0:
                blocker = QtCore.QSignalBlocker(self.speed_combo)
                self.speed_combo.setCurrentIndex(index)
                del blocker
        self.speed_combo.setToolTip(
            ('调整当前快照回放。' if controlling else '设置下一次快照回放。') +
            '1×按原始报价间隔等待，5×将间隔缩短为五分之一；单次最多等待60秒。' if enabled else
            'K 线回测自动尽快计算，快照回放速度不适用。可使用暂停和下一时刻逐步观察。' if mode == 'backtest' else
            '请在历史回测页选择快照回放；准备完成后可调整回放速度。')

    def change_replay_speed(self, *_):
        if not self.speed_combo.isEnabled():
            return
        state = self.states.get(self.active_id)
        if (self.pages.currentIndex() == 1 and state and state.get('mode') == 'replay'
                and state.get('status') in ('RUNNING', 'PAUSED')):
            state['speed'] = self.speed_combo.currentData()
            self.send_run('speed', value=state['speed'], quiet=True)

    def clear_execution_tables(self):
        # Selection changes invalidate all row identities before an async load arrives.
        self.data_jobs.cancel('trade')
        self.trade_context = self.trade_token = None
        for grid in (self.orders_table, self.trades_table, self.equity_table):
            grid.set_records([], None)
        populate(self.positions_table, [])
        self.log_view.clear()
        self.account_label.setText("尚未选择本工作区账户；请选择记录或创建新运行。")
        self.account_status.setText("虚拟账户：未选择")
        for value in self.metric_values.values():
            value.setText('—')
        self.refresh_execution_controls()

    def select_run(self, identity):
        state = self.states.get(identity)
        if not state or 'snapshot' not in state:
            metadata = next((item for item in self.store.runs() if item['id'] == identity), None)
            if metadata is None:
                return False
            state = {**metadata, **self.store.load_run(identity)}
            self.states[identity] = state
        destination = 1 if state['mode'] in ('backtest', 'replay') else 2
        self.workspace_run_ids[destination] = identity
        self.active_id = identity
        self.clear_execution_tables()
        self.switch_workspace(destination)
        self.display_run(state)
        self.engine_commands.put({"op": "load", "id": identity})
        return True

    def refresh_context_controls(self, *_):
        self.online_symbols_panel.setVisible(self.pages.currentIndex() in (2, 5)
                                            or self.mode_combo.currentData() == "live")

    def toggle_analysis_layout(self):
        if self.analysis_layout is None:
            self.analysis_layout = self.saveState()
            for dock in (self.library_dock, self.parameter_dock, self.bottom_dock):
                dock.hide()
            self.analysis_expand.setText("还原面板")
        else:
            saved, self.analysis_layout = self.analysis_layout, None
            self.restoreState(saved)
            self.analysis_expand.setText("展开分析")
        self.workspace_scroll.verticalScrollBar().setValue(0)

    def toggle_learning_layout(self):
        if self.learning_layout is not None:
            self.restore_learning_layout()
        else:
            self.learning_layout = self.saveState()
            for dock in (self.library_dock, self.parameter_dock, self.bottom_dock):
                dock.hide()
            self.metrics_panel.hide()
            self.lesson_reading.setText("还原面板")
        self.workspace_scroll.verticalScrollBar().setValue(0)

    def restore_learning_layout(self):
        if self.learning_layout is None:
            return
        layout, self.learning_layout = self.learning_layout, None
        self.restoreState(layout)
        self.metrics_panel.show()
        self.lesson_reading.setText("展开课程")

    def apply_theme(self):
        from astock.ui_components import DARK, LIGHT
        colors = DARK if self.theme_name == "dark" else LIGHT
        palette = self.palette()
        palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(colors["bg"]))
        palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(colors["surface"]))
        palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(colors["raised"]))
        palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(colors["bg"]))
        for role in (QtGui.QPalette.ColorRole.WindowText, QtGui.QPalette.ColorRole.Text,
                     QtGui.QPalette.ColorRole.ButtonText):
            palette.setColor(role, QtGui.QColor(colors["text"]))
        self.setPalette(palette)
        # Native scroll viewports and unoccupied tab-bar space also use the
        # application palette; leaving it at the Windows default paints white gaps.
        QtWidgets.QApplication.instance().setPalette(palette)
        self.setStyleSheet(stylesheet(self.theme_name))
        self.editor.theme(self.theme_name)
        self.backtest_overview.theme(self.theme_name)
        for chart in (self.preview_chart, self.result_chart, self.equity_chart):
            chart.theme(self.theme_name)

    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.store.set_setting("theme", self.theme_name)
        self.apply_theme()

    def refresh_library(self):
        if hasattr(self, "model_browser"):
            self.model_browser.refresh()
        if hasattr(self, "trading_tasks"):
            self.trading_tasks.refresh()
        self.library.clear()
        for title, entries in (("策略模板", [(n, "template", n) for n in TEMPLATES]),
                               ("已保存策略", [(x["name"], "saved", x["name"]) for x in self.store.strategies()]),
                               ("运行记录", [(x["name"] + " · " + STATUS.get(x["status"], x["status"]), "run", x["id"])
                                             for x in self.store.runs()[:40]])):
            parent = QtWidgets.QTreeWidgetItem([title])
            self.library.addTopLevelItem(parent)
            for name, kind, identity in entries:
                item = QtWidgets.QTreeWidgetItem([name])
                item.setData(0, QtCore.Qt.ItemDataRole.UserRole, (kind, identity))
                parent.addChild(item)
            parent.setExpanded(True)
        old = self.dataset_combo.currentData()
        self.datasets = list_datasets(self.root / "datasets")
        self.dataset_combo.blockSignals(True)
        self.dataset_combo.clear()
        for dataset in self.datasets:
            self.dataset_combo.addItem(display_name(dataset), dataset["id"])
            self.dataset_combo.setItemData(self.dataset_combo.count() - 1, source_summary(dataset), QtCore.Qt.ItemDataRole.ToolTipRole)
        selected = self.dataset_combo.findData(old)
        if selected >= 0:
            self.dataset_combo.setCurrentIndex(selected)
        self.dataset_combo.blockSignals(False)

    def library_clicked(self, item, column):
        value = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not value:
            return
        kind, identity = value
        if kind == "template":
            self.open_strategy_editor(kind, identity)
        elif kind == "saved":
            self.save_strategy(quiet=True)
            strategy = next(x for x in self.store.strategies() if x["name"] == identity)
            self.current_template = strategy["name"]
            self.strategy_title.setText(strategy["name"])
            self.editor.setPlainText(strategy["code"])
            self.rebuild_parameters(values=strategy["parameters"])
            self.switch_workspace(0)
            self.open_strategy_editor()
        else:
            self.select_run(identity)

    def load_template(self, name, save_current=True):
        if save_current:
            self.save_strategy(quiet=True)
        self.current_template = name
        self.editor.setPlainText(TEMPLATES[name]["code"])
        self.strategy_title.setText(name)
        self.strategy_description.setText(TEMPLATES[name]["description"] + "  /  Python 策略")
        self.rebuild_parameters()

    def rebuild_parameters(self, checked=False, values=None):
        try:
            schema = parameter_schema(self.editor.toPlainText())
            while self.param_form.rowCount():
                self.param_form.removeRow(0)
            self.parameters = {}
            for name, spec in schema.items():
                kind = spec.get("type", "float")
                value = (values or {}).get(name, spec["default"])
                if kind == "int":
                    widget = help_target(QtWidgets.QSpinBox(), 'window.MainWindow.rebuild_parameters.widget')
                    widget.setRange(int(spec.get("min", -1000000)), int(spec.get("max", 1000000)))
                    widget.setValue(int(value))
                elif kind == "float":
                    widget = help_target(QtWidgets.QDoubleSpinBox(), 'window.MainWindow.rebuild_parameters.widget2')
                    widget.setDecimals(4)
                    widget.setRange(float(spec.get("min", -1000000)), float(spec.get("max", 1000000)))
                    widget.setSingleStep(.05)
                    widget.setValue(float(value))
                elif kind == "bool":
                    widget = help_target(QtWidgets.QCheckBox(), 'window.MainWindow.rebuild_parameters.widget3')
                    widget.setChecked(bool(value))
                else:
                    widget = help_target(QtWidgets.QLineEdit(str(value)), 'window.MainWindow.rebuild_parameters.widget4')
                widget.setToolTip(spec.get("help", ""))
                widget.setAccessibleName(spec.get('label', name))
                name_label = label(spec.get("label", name))
                name_label.setToolTip(spec.get("help", ""))
                self.param_form.addRow(name_label, widget)
                self.parameters[name] = widget
                if hasattr(self, 'backtest_strategy_label'):
                    if isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
                        widget.valueChanged.connect(self.refresh_backtest_strategy)
                    elif isinstance(widget, QtWidgets.QCheckBox):
                        widget.toggled.connect(self.refresh_backtest_strategy)
                    else:
                        widget.textChanged.connect(self.refresh_backtest_strategy)
                if hasattr(self, "learning"):
                    if isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
                        widget.valueChanged.connect(lambda *_: self.learning.parameters_changed())
                    elif isinstance(widget, QtWidgets.QCheckBox):
                        widget.toggled.connect(lambda *_: self.learning.parameters_changed())
                    else:
                        widget.textChanged.connect(lambda *_: self.learning.parameters_changed())
            self.statusBar().showMessage("参数声明已检查，表单已更新", 4000)
            if hasattr(self, 'backtest_strategy_label'):
                self.refresh_backtest_strategy()
        except (SyntaxError, ValueError, TypeError) as e:
            if isinstance(e, SyntaxError):
                self.editor.goto_line(e.lineno or 1)
            self.error(str(e))

    def parameter_values(self):
        values = {}
        for name, widget in self.parameters.items():
            if isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
                values[name] = widget.value()
            elif isinstance(widget, QtWidgets.QCheckBox):
                values[name] = widget.isChecked()
            else:
                values[name] = widget.text()
        return values

    def save_strategy(self, checked=False, quiet=False):
        if not hasattr(self, "editor") or not self.editor.toPlainText():
            return
        self.store.save_strategy(self.current_template, self.editor.toPlainText(), self.parameter_values())
        if not quiet:
            self.learning.saved()
            self.statusBar().showMessage("策略和参数已保存", 4000)
            self.refresh_library()

    def import_strategy(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "导入可信任的 Python 策略", "", "Python (*.py)")
        if path:
            try:
                code = Path(path).read_text(encoding="utf-8-sig")
                parameter_schema(code)
                self.save_strategy(quiet=True)
                self.current_template = Path(path).stem
                self.editor.setPlainText(code)
                self.strategy_title.setText(self.current_template)
                self.rebuild_parameters()
                self.switch_workspace(0)
            except Exception as e:
                self.error(str(e))

    def _select_demo(self, kind):
        source = DEMO_BAR_SOURCE if kind == 'bar' else DEMO_QUOTE_SOURCE
        for i, meta in enumerate(self.datasets):
            if meta["demo"] and meta["kind"] == kind and meta["source"] == source:
                self.dataset_combo.setCurrentIndex(i)
                self.dataset_changed()
                return

    def dataset_changed(self, _=None):
        identity = self.dataset_combo.currentData()
        if not identity:
            self.cancel_preview()
            return
        if identity == self.preview_identity:
            return
        self.preview_identity = identity
        meta = next(x for x in self.datasets if x["id"] == identity)
        if not self.active_id:
            self.show_backtest_range(meta)
        self.mode_combo.setCurrentIndex(1 if meta["kind"] == "quote" else 0)
        self.refresh_replay_speed()
        self.preview_chart.set_data([], quote=meta["kind"] == "quote", meta=meta)
        self.data_badge.setText(display_name(meta) + " · 正在后台校验与加载预览…")
        self.cancel_preview_button.show()
        try:
            self.preview_token = self.data_jobs.start("preview", root=str(self.root / "datasets"), identity=identity)
        except Exception as e:
            self.preview_identity = None
            self.cancel_preview_button.hide()
            self.data_badge.setText("数据待核对 · " + str(e))

    def cancel_preview(self):
        self.data_jobs.cancel("preview")
        self.preview_token = self.preview_identity = None
        self.cancel_preview_button.hide()
        self.data_badge.setText("预览已取消 · 可重新选择数据；不影响已运行账户")

    def cancel_import(self):
        self.data_jobs.cancel("import")
        self.import_token = None
        self.cancel_import_button.hide()
        self.statusBar().showMessage("导入已取消，已有数据未改动", 6000)

    def data_job_message(self, message):
        kind = message["kind"]
        if kind == "live_rules":
            self.live_rule_message(message)
            return
        if kind == "trade":
            self.trade_job_message(message)
            return
        token = self.preview_token if kind == "preview" else self.import_token
        if self.closing or message["token"] != token:
            return
        if message["type"] == "progress":
            text = message["phase"] + (f" · {message['done']:,}/{message['total']:,} 条" if message.get("total") else "…")
            if kind == "preview":
                meta = next(x for x in self.datasets if x["id"] == self.preview_identity)
                self.data_badge.setText(display_name(meta) + " · " + text)
            else:
                self.statusBar().showMessage("导入：" + text)
            return
        if kind == "preview":
            self.preview_token = None
            self.cancel_preview_button.hide()
        else:
            self.import_token = None
            self.cancel_import_button.hide()
        if message["type"] == "error":
            if kind == "preview":
                self.preview_identity = None
                self.data_badge.setText("数据待核对 · " + message["message"])
            else:
                self.error("导入失败：" + message["message"], popup=False)
            return
        result = message["result"]
        meta = result["meta"]
        if kind == "import":
            try:
                publish_import(self.root / "datasets", message["request"], result)
                self.refresh_library()
                self.dataset_combo.setCurrentIndex(self.dataset_combo.findData(meta["id"]))
                self.statusBar().showMessage("数据导入完成，已通过完整性与行情校验", 7000)
            except Exception as error:
                self.error("导入失败：" + str(error), popup=False)
            return
        self.preview_chart.set_data(result["points"], symbol=result["symbol"], quote=meta["kind"] == "quote", meta=meta)
        self.data_badge.setText(origin_label(meta) + " · " + meta["period"]
                               + f" · {meta['count']:,} 条 · 预览最近 {len(result['points']):,} 条"
                               + "\n" + coverage_text(meta.get("quality")))

    def matching_config(self):
        return MatchConfig(commission_rate=dec(self.commission.value()) / 10000,
                           minimum_commission=dec(self.minimum_fee.value()),
                           participation=dec(self.participation.value()) / 100,
                           slippage_ticks=self.slippage.value(),
                           max_position_ratio=dec(self.position_limit.value()) / 100,
                           max_order_value=dec(self.order_limit.value()))

    def symbols(self):
        result = list(dict.fromkeys(symbol_code(s) for s in re.split(r"[,，;；\s]+", self.symbol_input.text()) if s))
        if not 1 <= len(result) <= 20:
            raise ValueError("请输入 1–20 个证券代码")
        return result

    def open_catalog(self):
        from astock.catalog_ui import CatalogDialog
        dialog = CatalogDialog(self.root, self.add_catalog_symbols, self)
        screen = self.screen().availableGeometry()
        dialog.resize(min(880, screen.width() - 40), min(620, screen.height() - 60))
        dialog.exec()
        dialog.deleteLater()

    def add_catalog_symbols(self, entries):
        from astock.catalog import add_symbols
        before = set(self.symbols()) if self.symbol_input.text().strip() else set()
        text = add_symbols(self.symbol_input.text(), entries)
        self.symbol_input.setText(text)
        self.symbol_input.setCursorPosition(0)
        self.store.set_setting("watchlist", text)
        count = len(set(text.split(",")) - before)
        return (f"新增 {count} 个标的，当前共 {len(text.split(','))} 个。"
                + ("重新连接行情后生效；已运行策略继续使用原有标的。" if self.connected
                   else "回到实时仿真，点击「连接行情」。"))

    def start_historical(self):
        meta = next((m for m in self.datasets if m['id'] == self.dataset_combo.currentData()), {})
        if meta.get('kind') == 'quote':
            self.refresh_backtest_strategy()
            self.mode_combo.setCurrentIndex(self.mode_combo.findData('replay'))
            self.start_run(mode='replay')
        else:
            self.start_backtest()

    def start_backtest(self):
        self.refresh_backtest_strategy()
        meta = next((m for m in self.datasets if m["id"] == self.dataset_combo.currentData()), None)
        if not meta or meta["kind"] != "bar":
            self.error("历史回测需要 K 线数据。请在数据中心选择日线或分钟线；报价快照请使用快照回放。")
            return
        self.mode_combo.setCurrentIndex(self.mode_combo.findData("backtest"))
        self.start_run(mode="backtest")

    def start_run(self, checked=False, autoplay=True, mode=None):
        if self.start_pending:
            return
        try:
            mode = mode or self.mode_combo.currentData()
            ast.parse(self.editor.toPlainText())
            schema = parameter_schema(self.editor.toPlainText())
            if set(schema) != set(self.parameters):
                self.rebuild_parameters()
            params = self.parameter_values()
            request = {"op": "start", "mode": mode, "name": self.current_template,
                       "code": self.editor.toPlainText(), "parameters": params,
                       "initial": self.capital.value(), "config": self.matching_config(),
                       "dataset": self.dataset_combo.currentData(),
                       "symbols": self.symbols() if mode in ("live", "manual") else [],
                       "autoplay": autoplay, "speed": self.speed_combo.currentData()}
            if mode == "backtest":
                options = self.backtest_options.get(request["dataset"])
                if options:
                    request["backtest_window"] = {key: options[key] for key in ("start", "end")}
                    request["benchmark_symbol"] = options["benchmark"]
            if mode == "manual":
                request["code"], request["name"] = "", "手动练习账户"
            self.learning.tag_request(request)
            self.save_strategy(quiet=True)
            if mode in ("live", "manual"):
                self.prepare_live_request(request)
            else:
                self.dispatch_run_request(request)
        except Exception as e:
            if isinstance(e, SyntaxError):
                self.editor.goto_line(e.lineno or 1)
                self.switch_workspace(0)
            self.error(str(e))

    def dispatch_run_request(self, request):
        mode = request["mode"]
        if mode == "manual":
            try:
                current_symbol = symbol_code(self.manual_symbol.text())
            except ValueError:
                current_symbol = ""
            if current_symbol not in request["symbols"]:
                self.manual_symbol.setText(request["symbols"][0])
        if mode in ("live", "manual") and not self.connected:
            self.toggle_market()
        self.pending_run_mode = mode
        self.engine_commands.put(request)
        self.start_pending = True
        self.backtest_start_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.start_button.setText("正在创建…")
        self.learning.render()
        self.notice.hide()
        self.statusBar().showMessage("正在创建独立账户与策略进程…")
        self.switch_workspace(2 if mode in ("live", "manual") else 1)

    def prepare_live_request(self, request):
        if self.live_rule_token:
            return
        token = self.data_jobs.start("live_rules", root=str(self.root), symbols=request["symbols"])
        self.live_rule_token, self.live_rule_request = token, request
        self.start_pending = True
        self.start_button.setEnabled(False)
        self.start_button.setText("核对当日规则…")
        self.symbol_input.setEnabled(False)
        self.refresh_live_rule_button.setEnabled(False)
        self.cancel_live_rule_button.show()
        self.live_rule_status.setText("正在后台核对 ETF 当日资料；完成前不创建账户或改变账户规则。")
        self.switch_workspace(2)

    def cancel_live_rule_preparation(self):
        self.data_jobs.cancel("live_rules")
        self.live_rule_token = self.live_rule_request = None
        self.start_pending = False
        self.start_button.setEnabled(True)
        self.start_button.setText("▶  开始运行")
        self.symbol_input.setEnabled(True)
        self.refresh_live_rule_button.setEnabled(True)
        self.cancel_live_rule_button.hide()
        self.live_rule_status.setText("准备已取消，已有账户及规则保持原样。")

    def refresh_active_live_rules(self):
        if self.start_pending:
            return
        state = self.states.get(self.active_id)
        if not state or state["mode"] not in ("live", "manual") or state["status"] != "PAUSED":
            self.live_rule_status.setText("请先选择并暂停实时账户，再更新当日规则；已有资金和持仓保留。")
            return
        self.prepare_live_request({"op": "refresh_live_rules", "id": self.active_id,
                                   "symbols": list(state["manifest"]["rules"])})

    def live_rule_message(self, message):
        if self.closing or message["token"] != self.live_rule_token or self.live_rule_request is None:
            return
        if message["type"] == "progress":
            self.live_rule_status.setText(message["phase"] + "… 可取消准备。")
            return
        request = self.live_rule_request
        self.cancel_live_rule_preparation()
        if message["type"] == "error":
            self.live_rule_status.setText("当日规则准备失败，账户未改变：" + message["message"])
            return
        try:
            from astock.catalog import load_catalog, publish_catalog
            result = message["result"]
            if result["catalog"] is not None:
                current, _ = load_catalog(self.root)
                publish_catalog(self.root, current, result["catalog"])
            self.live_rule_status.setText("当日资料已核对：" + result["valid_day"] + "。账户创建和更新由引擎再次检查。")
            if request["op"] == "start":
                self.dispatch_run_request(request)
            else:
                self.engine_commands.put(request)
        except Exception as error:
            self.live_rule_status.setText("当日规则准备失败，账户未改变：" + str(error))

    def start_live(self, manual):
        if manual:
            self.live_tabs.setCurrentWidget(self.manual_form)
        self.mode_combo.setCurrentIndex(2)
        self.start_run(mode="manual" if manual else "live")

    def clear_run_selection(self):
        """Preparing a new exercise must not present the previous account as selected."""
        old_state = self.states.get(self.active_id)
        if old_state:
            self.workspace_run_ids[1 if old_state['mode'] in ('backtest', 'replay') else 2] = None
        elif self.learning.lesson is not None:
            self.workspace_run_ids[2 if self.mode_combo.currentData() == 'live' else 1] = None
        self.active_id = None
        self.data_jobs.cancel("trade")
        self.backtest_overview.update_state(None)
        self.trade_context = self.trade_token = None
        self.pause_action.setEnabled(False)
        self.resume_action.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.mode_badge.setText(MODES[self.mode_combo.currentData()] + " · 待创建")
        self.account_status.setText("虚拟账户：待创建")
        self.account_status.setToolTip("本节将建立新的独立账户；已有账户保留在运行记录中。")
        self.account_label.setText("准备新的独立虚拟账户 · 已有账户保留在左侧运行记录中")
        for widget in self.metric_values.values():
            widget.setText("—")
        for grid in (self.orders_table, self.trades_table, self.equity_table, self.activity_orders, self.activity_trades):
            grid.set_records([], None)
        self.activity_logs.clear()
        meta = next((m for m in self.datasets if m["id"] == self.dataset_combo.currentData()), {})
        self.show_backtest_range(meta)
        self.backtest_progress.setText("尚未推进行情。开始运行可自动完成；下一时刻用于单步调试。")
        populate(self.positions_table, [])
        self.equity_chart.set_data([])
        self.result_chart.set_data([])
        self.result_description.setText("尚未创建本节账户；运行后显示本次结果。")
        self.trade_explanation.clear()
        self.equity_note.clear()
        self.log_view.clear()
        self.manifest_text.clear()
        from astock.backtest_analysis import diagnostics_html
        self.diagnostics.setHtml(diagnostics_html([], 100000))
        self.progress.setValue(0)
        self.progress.setFormat("待创建")

    def step_run(self):
        if self.start_pending:
            return
        state = self.states.get(self.active_id)
        if state and state.get('mode') in ('backtest', 'replay') and self.pages.currentIndex() == 1:
            # Debug the selected account even if the next-run data or editor has changed.
            if state['status'] == 'RUNNING':
                self.send_run('pause')
                self.send_run('step')
            elif state['status'] == 'PAUSED':
                self.send_run('step')
            else:
                self.statusBar().showMessage('该历史运行已结束；使用“开始回测”创建新的独立运行。', 5000)
            return
        selected_mode = self.mode_combo.currentData()
        if selected_mode == "live":
            self.statusBar().showMessage("实时仿真由行情驱动；单步操作用于历史回测或快照回放", 5000)
            return
        if state and (state["mode"] != selected_mode or
                      (state.get("manifest", {}).get("dataset") or {}).get("id") != self.dataset_combo.currentData()):
            state = None
        if state and state["status"] == "PAUSED":
            self.send_run("step")
        elif state and state["status"] == "RUNNING":
            self.send_run("pause")
            self.send_run("step")
        else:
            self.start_run(autoplay=False)
            self.step_after_start = self.start_pending

    def send_run(self, op, quiet=False, **kwargs):
        if not self.active_id:
            if not quiet:
                self.statusBar().showMessage("请先运行策略或选择运行记录", 5000)
            return
        state = self.states.get(self.active_id)
        page = self.pages.currentIndex()
        allowed = ("backtest", "replay") if page == 1 else ("live", "manual") if page == 2 else ()
        if not state or state.get("mode") not in allowed:
            self.statusBar().showMessage("请在对应工作区选择账户；历史回测与模拟交易的控制互不通用。", 5000)
            return
        if op == 'speed' and (state.get('mode') != 'replay' or state.get('status') not in ('RUNNING', 'PAUSED')):
            return
        if op == "manual_order" and (not state or state.get("mode") != "manual"):
            self.statusBar().showMessage("请先选择手动练习账户。", 5000)
            return
        self.engine_commands.put({"op": op, "id": self.active_id, **kwargs})

    def toggle_market(self):
        try:
            if self.connected:
                self.market_commands.put({"op": "stop"})
                self.connected = False
                self.market_metrics = {"status": "未连接"}
                self.connect_button.setText("连接行情")
                self.record_check.setChecked(False)
            else:
                self.market_commands.put({"op": "connect", "symbols": self.symbols()})
                self.connected = True
                self.quotes.clear()
                self.market_metrics = {"status": "连接中"}
                self.connect_button.setText("断开行情")
                self.market_status.setText("正在连接腾讯报价…")
            self.refresh_market_status()
        except Exception as e:
            self.error(str(e))

    def use_opposite_price(self):
        try:
            q = self.quotes.get(symbol_code(self.manual_symbol.text()))
            if not q:
                raise ValueError("该标的尚无报价；请先加入右侧在线标的并连接行情")
            value = q.ask if self.manual_side.currentIndex() == 0 else q.bid
            if value <= 0:
                raise ValueError("当前缺少对手报价")
            from astock.rules import default_rule
            tick = float(default_rule(q.symbol).tick)
            # 默认补足配置的不利滑点，使快速填写的限价仍有成交空间。
            value = float(value) + (1 if self.manual_side.currentIndex() == 0 else -1) * self.slippage.value() * tick
            self.manual_price.setValue(value)
        except Exception as e:
            self.error(str(e))

    def manual_order(self):
        try:
            order = {"symbol": symbol_code(self.manual_symbol.text()),
                     "side": "BUY" if self.manual_side.currentIndex() == 0 else "SELL",
                     "quantity": self.manual_qty.value(), "price": dec(self.manual_price.value()), "reason": "手动练习委托"}
            self.send_run("manual_order", order=order)
            self.bottom_tabs.setCurrentIndex(1)
        except Exception as e:
            self.error(str(e))

    def cancel_selected(self):
        order = self.orders_table.current_record()
        if order and self.orders_table.run_id == self.active_id:
            self.send_run("cancel", order_id=order.id)

    def poll(self):
        started = time.perf_counter()
        display_needed = library_needed = market_needed = False
        for _ in range(80):
            try:
                message = self.output.get_nowait()
            except Empty:
                break
            kind = message["type"]
            if kind == "engine_ready":
                self.status_text.setText("引擎就绪 · 虚拟账户")
                self.refresh_library()
            elif kind == "run_created":
                self.start_pending = False
                self.start_button.setEnabled(True)
                self.start_button.setText("▶  开始运行")
                created = self.states.get(message['id']) or next(
                    (entry for entry in self.store.runs() if entry['id'] == message['id']), {})
                created_mode = created.get('mode') or message.get('mode') or self.pending_run_mode
                destination = 2 if created_mode in ("live", "manual") else 1
                self.workspace_run_ids[destination] = message["id"]
                if self.pages.currentIndex() == destination:
                    self.active_id = message["id"]
                    self.clear_execution_tables()
                self.backtest_start_button.setEnabled(True)
                self.pending_run_mode = None
                if self.step_after_start:
                    self.step_after_start = False
                    self.engine_commands.put({"op": "step", "id": message["id"]})
                self.statusBar().showMessage("运行已创建，使用独立虚拟账户", 5000)
                self.refresh_library()
            elif kind == "run_update":
                previous = self.states.get(message["id"], {}).get("status")
                self.states[message["id"]] = message
                self.learning.observe(message)
                if message["id"] == self.active_id:
                    display_needed = True
                if previous != message["status"]:
                    library_needed = True
            elif kind == "quotes":
                self.quotes.update({q.symbol: q for q in message["quotes"]})
                self.learning.observe_quotes(message["quotes"])
                market_needed = True
            elif kind == "market_status":
                self.market_metrics = message
                market_needed = True
            elif kind == "recorded":
                self.refresh_library()
                if message.get("meta"):
                    self.statusBar().showMessage("行情录制已保存，可在数据中心选择回放", 7000)
            elif kind == "recording_sealed":
                self.show_operation("recover", message["directory"])
            elif kind == "recording_state":
                with QtCore.QSignalBlocker(self.record_check):
                    self.record_check.setChecked(message["enabled"])
            elif kind == "history_progress":
                self.statusBar().showMessage(message["message"])
            elif kind == "history_done":
                self.refresh_library()
                index = self.dataset_combo.findData(message["meta"]["id"])
                self.dataset_combo.setCurrentIndex(index)
                meta = message["meta"]
                if not meta.get("corporate_actions_verified"):
                    self.error("下载已完成，数据已保存，但暂不能回测：\n" + meta.get("notes", "权益资料待核对")
                               + "\n可下载不跨上述权益日期的区间，或补充完整权益数据包。", popup=False)
                self.statusBar().showMessage(f"已保存 {meta['count']} 条 · {meta['source']} · "
                                            f"{meta['start'][:16]} 至 {meta['end'][:16]}；请检查质量说明", 15000)
            elif kind == "error":
                if self.live_rule_token is None:
                    self.start_pending = False
                    self.step_after_start = False
                    self.start_button.setEnabled(True)
                    self.start_button.setText("▶  开始运行")
                    self.backtest_start_button.setEnabled(True)
                    self.pending_run_mode = None
                self.learning.render()
                self.error(message.get("message", "未知错误"), popup=False)
                matches = re.findall(r'File "strategy.py", line (\d+)', message.get("traceback", "") + message.get("message", ""))
                if matches:
                    self.editor.goto_line(int(matches[-1]))
            if time.perf_counter() - started > .016:
                break
        if library_needed:
            self.refresh_library()
        if market_needed:
            self.refresh_market_status()
        if display_needed and self.active_id in self.states:
            self.display_run(self.states[self.active_id])
        if self.worker_enabled and not self.closing:
            for process in self.processes:
                if process.exitcode is not None:
                    self.status_text.setText(f"{process.name} 已退出 ({process.exitcode})，请重启软件")

    def refresh_market_status(self):
        from astock.rules import continuous_session, default_rule
        current = now_cn()
        status = self.market_metrics.get("status", "未连接")
        interval = self.market_metrics.get("interval")
        ages = [(current - q.time).total_seconds() for q in self.quotes.values()]
        in_session = any(continuous_session(current, default_rule(q.symbol)) for q in self.quotes.values())
        badge = status
        phase = ""
        if status == "已连接" and ages:
            if not in_session:
                badge, phase = "休市报价", " · 非连续竞价时段，仅展示报价"
            elif min(ages) < -2:
                badge, phase = "时间异常", " · 来源时间异常，暂停相关标的撮合"
            elif max(ages) > 15:
                badge, phase = "数据过期", " · 报价已过期，暂停相关标的撮合"
        elif status == "已连接":
            badge = "等待报价"
        elif status.startswith("连接失败"):
            badge = "重试中"
        text = status + (f" · 实际间隔 {interval:.1f}s" if interval else "")
        text += f" · 最大数据年龄 {max(ages):.1f}s" if ages else ""
        text += phase + " · 快照近似仿真"
        if self.market_metrics.get("message"):
            text += "\n" + self.market_metrics["message"]
        self.market_status.setText(text)
        self.market_overview_status.setText(text)
        self.market_badge.setText("行情：" + badge)
        self.market_badge.setToolTip(text)
        self.display_quotes()

    def display_quotes(self):
        rows = []
        for q in self.quotes.values():
            rows.append([f"{q.symbol}  {q.name}", f"{q.last:f}", str(q.bid), str(q.ask),
                         q.time.strftime("%m-%d %H:%M:%S"), f"{(now_cn()-q.time).total_seconds():.1f}"])
        populate(self.quote_table, rows)
        populate(self.market_overview_table, rows)

    def display_run(self, state):
        historical = state["mode"] in ("backtest", "replay")
        domain = 1 if historical else 2
        if self.workspace_run_ids[domain] is None and self.active_id == state['id']:
            self.workspace_run_ids[domain] = state['id']
        page = self.pages.currentIndex()
        if page in (1, 2) and page != domain:
            return
        if self.workspace_run_ids[domain] not in (None, state['id']):
            return
        self.trading_tasks.refresh()
        result, snapshot = state.get("result", {}), state.get("snapshot", {})
        if not result.get('statistics') or 'account' not in snapshot:
            self.clear_execution_tables()
            self.account_status.setText(f"虚拟账户：{state['id'][:6]} · 等待完整记录")
            return
        stats, account = result["statistics"], snapshot["account"]
        self.pause_action.setEnabled(state["status"] == "RUNNING")
        self.resume_action.setEnabled(state["status"] == "PAUSED")
        self.step_action.setEnabled(self.mode_combo.currentData() in ("backtest", "replay"))
        self.stop_button.setEnabled(state["status"] in ("RUNNING", "PAUSED"))
        self.metric_values["equity"].setText(f"{stats['equity']:,.2f}")
        self.metric_values["return"].setText(f"{stats['return']:+.2%}")
        self.metric_values["drawdown"].setText(f"{stats['max_drawdown']:.2%}")
        self.metric_values["fees"].setText(f"{stats['fees']:,.2f}")
        self.mode_badge.setText(MODES[state["mode"]] + " · " + STATUS.get(state["status"], state["status"]))
        self.account_status.setText(f"虚拟账户：{state['id'][:6]}")
        self.account_status.setToolTip(f"{state['name']} / {state['id']} · 可用资金 {float(state.get('available', account.cash)):,.2f}")
        self.account_label.setText(f"{state['name']} / {state['id'][:6]}  |  可用 {float(state.get('available', account.cash)):,.2f}"
                                   f"  |  冻结 {float(state.get('frozen', 0)):,.2f}  |  虚拟资金")
        rows = [[s, p.quantity, state.get("available_positions", {}).get(s, "—"), f"{p.cost:,.2f}",
                 str(p.last), f"{p.quantity*p.last-p.cost:+,.2f}"] for s, p in account.positions.items() if p.quantity]
        populate(self.positions_table, rows)
        self.orders_table.set_records(snapshot["orders"], state["id"])
        self.trades_table.set_records(snapshot["trades"], state["id"])
        if historical:
            self.activity_orders.set_records(snapshot["orders"], state["id"])
            self.activity_trades.set_records(snapshot["trades"], state["id"])
        self.equity_table.set_records(snapshot.get("equity_entries", []), state["id"])
        receivable = sum((dec(item["amount"]) for item in account.receivables), dec(0))
        paid = sum((entry.cash_delta for entry in snapshot.get("equity_entries", [])), dec(0))
        self.equity_note.setText(f"应收分红 {receivable:,.2f} 元 · 累计到账 {paid:,.2f} 元\n" + accounting_note(snapshot))
        log = "\n".join(f"{x['time'].strftime('%Y-%m-%d %H:%M:%S')}  {log_message(x)}" for x in result["logs"])
        if historical and self.activity_logs.toPlainText() != log:
            self.activity_logs.setPlainText(log)
        if self.log_view.toPlainText() != log:
            self.log_view.setPlainText(log)
            self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
        if hasattr(self, "strategy_dialog"):
            self.strategy_dialog.output.setPlainText(log)
        if historical:
            self.equity_chart.set_data(result["curve"])
            self.refresh_diagnostics()
            symbols = list(result["prices"])
            if [self.chart_symbol.itemText(i) for i in range(self.chart_symbol.count())] != symbols:
                self.chart_symbol.blockSignals(True)
                self.chart_symbol.clear()
                self.chart_symbol.addItems(symbols)
                self.chart_symbol.blockSignals(False)
            self.refresh_result_chart()
            self.backtest_overview.update_state(state)
            total = result.get("total", 0)
            self.progress.setMaximum(max(1, total))
            self.progress.setValue(result.get("index", 0))
            self.progress.setFormat(f"{result.get('index', 0)}/{total}" if total else "在线")
            meta = state["manifest"].get("dataset") or {}
            self.show_backtest_range(meta)
            selected = state["manifest"].get("backtest_window")
            if selected:
                self.backtest_range.setText(
                    f"本次回测：{selected['start']} 至 {selected['end']}（含首尾日期，北京时间）\n"
                    f"实际行情：{str(selected['actual_start'])[:19]} 至 {str(selected['actual_end'])[:19]} · "
                    f"基准 {state['manifest']['benchmark_symbol']} · 周期 {meta.get('period', '—')} · "
                    + origin_label(meta))
            clock = snapshot.get("clock")
            current = clock.strftime("%Y-%m-%d %H:%M:%S") if clock and result.get("index", 0) else "尚未开始"
            self.backtest_progress.setText(
                f"已读取 {result.get('index', 0)}/{total} 条行情 · 当前模拟时间 {current}\n"
                f"提交 {len(snapshot['orders'])} 笔委托 → {len(snapshot['trades'])} 笔成交。"
                "一条行情不等于一笔交易；买卖过程见「操作记录」。")
            fingerprint = state.get('manifest', {}).get('code_sha256', '')[:8]
            self.result_description.setText(f"当前结果 · {state['name']} / {state['id'][:8]} · {STATUS.get(state['status'], state['status'])} · 源码 {fingerprint}\n"
                                            f"{display_name(meta)} · {stats['trades']} 笔成交"
                                            + (" · 数据覆盖待核对" if meta.get("quality", {}).get("status") == "review" else ""))
            self.result_description.setToolTip(coverage_text(meta.get("quality")))
        from html import escape
        from astock.domain import dumps
        archive = state["manifest"].get("input_archive")
        display_manifest = {k: v for k, v in state["manifest"].items() if k != "code"}
        if archive:
            display_manifest["input_archive"] = {k: v for k, v in archive.items() if k != "parts"}
            display_manifest["input_archive"]["part_count"] = len(archive["parts"])
        capture_info = (f"<p>自动留存 {archive['count']:,} 条输入 · {escape(archive['state'])}。"
                        "停止后可在数据中心选择“运行留存”回放；沿用当时的接收延迟，"
                        "手动下单、暂停和撤单不自动重演。</p>") if archive else ""
        rule_info = ""
        observations = state["manifest"].get("live_rule_observations")
        if observations:
            audit = observations[-1]
            items = []
            for row in audit["records"]:
                ref = row["etf_reference"]
                items.append(f"<li>{escape(row['symbol'])} · {escape(row['name'])}：T+{ref['t_plus']}，"
                             f"涨跌幅 {dec(ref['limit_rate']) * 100:g}%</li>")
            rule_info = (f"<h3>本账户 ETF 规则</h3><p>适用日期：{escape(audit['valid_day'])}。"
                         "T+0 允许当日买入后卖出；T+1 须到下一交易日。跨日暂停后更新，原有资金和持仓保留。</p><ul>"
                         + "".join(items) + "</ul>")
            if not self.live_rule_token:
                day = now_cn().date().isoformat()
                self.live_rule_status.setText(f"本账户 ETF 规则：{audit['valid_day']} · {len(items)} 只。"
                                              + ("已跨日，请暂停后更新当日规则。" if audit["valid_day"] != day
                                                 else "可在「模拟交易 → 账户规则与依据」查看各标的规则。"))
        elif not self.live_rule_token:
            self.live_rule_status.setText("本账户使用保存的股票标准规则。" if state["mode"] in ("live", "manual")
                                          else "请选择实时账户查看或更新当日 ETF 规则。")
        manifest_view = self.manifest_text if historical else self.live_manifest_text
        manifest_view.setHtml("<h3>运行配置与数据版本</h3><p>" + escape(state["manifest"].get("model", "")) +
                                  "</p>" + rule_info + capture_info + "<p>基准为 " +
                                  escape(str(state["manifest"].get("benchmark_symbol", "默认标的"))) +
                                  " 的价格买入持有，不含分红再投资。</p><pre>" +
                                  escape(dumps(display_manifest)) + "</pre>")
        self.refresh_backtest_strategy()
        self.refresh_execution_controls()

    def refresh_diagnostics(self, _=None):
        if self.result_tabs.currentWidget() is not self.diagnostics:
            return
        state = self.states.get(self.active_id)
        from astock.backtest_analysis import diagnostics_html
        if state:
            self.diagnostics.setHtml(diagnostics_html(state["result"]["curve"],
                                                     state["snapshot"]["account"].initial))
        else:
            self.diagnostics.setHtml(diagnostics_html([], 100000))

    def refresh_result_chart(self, _=None):
        state = self.states.get(self.active_id)
        if not state:
            return
        symbol = self.chart_symbol.currentText()
        context = self.trade_context
        if context and (context["run_id"] != self.active_id or context["symbol"] != symbol):
            self.data_jobs.cancel("trade")
            self.trade_context = self.trade_token = None
            context = None
        points = context["points"] if context else state["result"]["prices"].get(symbol, [])
        self.result_chart.set_data(points, state["snapshot"]["trades"],
                                   symbol, state["mode"] != "backtest", meta=state.get('manifest', {}).get('dataset'))
        if context:
            self.result_chart.locate(context["at"])
        else:
            self.result_chart.cursor.hide()

    def clear_trade_context(self):
        self.data_jobs.cancel("trade")
        self.trade_token = self.trade_context = None
        self.trade_explanation.setText("已返回当前账户的最新图表；选择成交记录可查看历史区间。")
        self.refresh_result_chart()

    def trade_job_message(self, message):
        context = self.trade_context
        if self.closing or not context or message["token"] != self.trade_token or context["run_id"] != self.active_id:
            return
        if message["type"] == "progress":
            self.trade_explanation.setText(context["description"] + " · " + message["phase"] + "…")
            return
        self.trade_token = None
        if message["type"] == "error":
            self.trade_explanation.setText(context["description"] + " · 定位失败：" + message["message"])
            return
        context["points"] = message["result"]["points"]
        self.refresh_result_chart()
        self.trade_explanation.setText(context["description"] + " · 原始行情区间；返回最新行情可退出定位")
        self.learning.reviewed_trade(context["run_id"], context["trade_id"])

    def configure_backtest(self):
        from astock.backtest_setup import BacktestSetup
        meta = next((m for m in self.datasets if m["id"] == self.dataset_combo.currentData()), None)
        options = self.backtest_options.get(meta['id'], {}) if meta else {}
        dialog = BacktestSetup(meta, options, self.capital.value(), self,
                               datasets=self.datasets, saved_options=self.backtest_options)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            selected = dialog.selected_meta()
            self.dataset_combo.setCurrentIndex(self.dataset_combo.findData(selected['id']))
            if selected.get('kind') == 'bar':
                self.backtest_options[selected['id']] = dialog.options()
            self.capital.setValue(dialog.capital.value())
            self.mode_combo.setCurrentIndex(self.mode_combo.findData('replay' if selected.get('kind') == 'quote' else 'backtest'))
            self.refresh_backtest_strategy()
            self.statusBar().showMessage("回测设置已保存；开始运行将创建新账户，已有结果不变。", 15000)

    def show_backtest_range(self, meta):
        def display(value):
            return str(value).replace("T", " ")[:19] if value else "未知"
        if not meta:
            self.backtest_range.setText("在线行情由实际收到的报价驱动；不是历史区间回测。")
            return
        origin = origin_label(meta)
        self.backtest_range.setText(
            f"数据区间（北京时间）：{display(meta.get('start'))} 至 {display(meta.get('end'))}\n"
            f"{origin} · 周期 {meta.get('period', '—')} · {meta.get('count', 0)} 条行情 · "
            "本次运行使用整个数据区间；多个证券同一时刻分别计数。")

    def select_trade(self, source=None):
        state = self.states.get(self.active_id)
        source = source if source is not None else self.trades_table
        trade = source.current_record()
        if not state or not trade or source.run_id != self.active_id:
            return
        if state["mode"] in ("live", "manual"):
            QtWidgets.QMessageBox.information(self, "模拟成交详情",
                f"账户：{state['name']} / {state['id']}\n{trade.time:%Y-%m-%d %H:%M:%S} · {trade.symbol}\n"
                f"{trade.side} {trade.quantity} @ {trade.price} · 费用 {trade.fee}\n{trade.reason}")
            self.learning.reviewed_trade(state["id"], trade.id)
            return
        self.data_jobs.cancel("trade")
        self.trade_context = self.trade_token = None
        self.chart_symbol.setCurrentText(trade.symbol)
        self.result_tabs.setCurrentWidget(self.trade_page)
        self.switch_workspace(1)
        description = f"{trade.id} · {trade.time:%Y-%m-%d %H:%M:%S} · {trade.reason}"
        points = state["result"]["prices"].get(trade.symbol, [])
        in_cache = any(point["time"] == trade.time for point in points)
        self.trade_context = {"run_id": self.active_id, "symbol": trade.symbol, "at": trade.time,
                              "points": points if in_cache else [], "description": description, "trade_id": trade.id}
        self.refresh_result_chart()
        self.trade_explanation.setText(description)
        QtCore.QTimer.singleShot(0, self.workspace_scroll, lambda: self.workspace_scroll.ensureWidgetVisible(self.trade_explanation)
                                if not self.closing else None)
        self.context_help.setText(f"这笔成交：{trade.quantity} 股/份 @ {trade.price}；费用 {trade.fee}。\n{trade.reason}")
        if in_cache:
            self.learning.reviewed_trade(state["id"], trade.id)
        if not in_cache:
            self.trade_explanation.setText(description + " · 正在后台定位原始行情…")
            self.trade_token = self.data_jobs.start("trade", root=str(self.root),
                dataset=(state["manifest"].get("dataset") or {}).get("id"),
                archive=state["manifest"].get("input_archive"), symbol=trade.symbol, at=trade.time,
                until=state["snapshot"]["clock"])

    def show_lesson(self, index):
        self.equity_lesson_button.setVisible(index == 2)
        self.lesson_index = index
        lesson = LESSONS[index]
        self.lesson_body.setHtml("<style>body{font-family:'Microsoft YaHei';line-height:1.8}h2{color:#57bda4}</style>" + lesson["html"])
        self.lesson_goal.setText(lesson["goal"])
        self.lesson_action.setText(lesson["button"])
        self.lesson_action.show()
        self.lesson_done_button.show()
        self.lesson_steps.show()
        self.lesson_offline.setVisible(index == 3)
        self.lesson_resume_guide.setVisible(self.learning.lesson is not None)
        for number, widget in enumerate(self.lesson_buttons):
            widget.setCheckable(True)
            widget.setChecked(number == index)
        self.learning.render()

    def show_glossary(self):
        self.equity_lesson_button.hide()
        self.lesson_body.setHtml(GLOSSARY)
        self.lesson_action.hide()
        self.lesson_offline.hide()
        self.lesson_steps.hide()
        self.lesson_done_button.hide()
        self.lesson_goal.setText("点击上方课程按钮返回互动教程。")
        self.open_practice()

    def complete_lesson(self):
        self.completed.add(self.lesson_index)
        self.store.set_setting("lessons_completed", sorted(self.completed))
        self.learning.render()

    def lesson_do(self):
        self.learning.begin(self.lesson_index)

    def prepare_equity_lesson(self):
        from astock.equity_lesson import CODE, ensure_equity_lesson
        self.save_strategy(quiet=True)
        meta = ensure_equity_lesson(self.root / "datasets")
        self.refresh_library()
        self.dataset_combo.setCurrentIndex(next(i for i, m in enumerate(self.datasets) if m["id"] == meta["id"]))
        self.current_template = "分红与送转练习"
        self.strategy_title.setText(self.current_template)
        self.strategy_description.setText("离线合成练习 · 单步观察登记、到账、可卖日期")
        self.editor.setPlainText(CODE)
        self.rebuild_parameters()
        self.mode_combo.setCurrentIndex(self.mode_combo.findData("backtest"))
        self.active_id = None  # 单步创建练习账户，不推进此前选中的账户。
        self.bottom_dock.show()
        self.bottom_tabs.setCurrentIndex(4)
        self.switch_workspace(0)
        self.statusBar().showMessage("练习已载入。点击「单步」逐日推进，在「权益流水」查看变化。", 15000)

    def show_api(self):
        from shiboken6 import isValid
        from astock.strategy_reference import REFERENCE
        dialog = getattr(self, 'strategy_api_dialog', None)
        if dialog is None or not isValid(dialog):
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle('策略接口 · AStock')
            dialog.setModal(False)
            dialog.instruction_preview = True
            available = self.screen().availableGeometry()
            dialog.resize(min(800, available.width() - 40), min(650, available.height() - 80))
            layout = QtWidgets.QVBoxLayout(dialog)
            browser = help_target(QtWidgets.QTextBrowser(), 'window.MainWindow.show_api.browser')
            browser.setMarkdown(REFERENCE)
            layout.addWidget(browser, 1)
            actions = help_target(QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close), 'window.MainWindow.show_api.actions')
            actions.rejected.connect(dialog.close)
            layout.addWidget(actions)
            self.strategy_api_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def open_data_center(self):
        self.refresh_library()
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("数据中心 · 覆盖范围与质量")
        dialog.resize(1000, 620)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(label("选择实际存在的数据，保留来源和质量说明", "title"))
        grid = help_target(table(["名称", "类型", "起始", "结束", "记录数", "权益核对", "数据覆盖"]), 'window.MainWindow.open_data_center.grid')
        datasets = list_datasets(self.root / "datasets")
        populate(grid, [[display_name(m), origin_label(m), m["start"][:16], m["end"][:16],
                         m["count"], "已核对" if m["corporate_actions_verified"] else "暂不能回测 · 查看下方原因",
                         coverage_text(m.get("quality"))] for m in datasets])
        for index, meta in enumerate(datasets):
            grid.item(index, 0).setData(QtCore.Qt.ItemDataRole.UserRole, meta["id"])
        layout.addWidget(grid, 1)
        notes = help_target(QtWidgets.QTextBrowser(), 'window.MainWindow.open_data_center.notes')
        notes.setMaximumHeight(150)
        layout.addWidget(notes)
        def selected_index():
            rows = grid.selectionModel().selectedRows()
            return rows[0].row() if rows else -1
        def selected():
            i = selected_index()
            if i >= 0:
                from astock.rules import rules_summary
                m = datasets[i]
                notes.setPlainText(source_summary(m) + '\n' + m["notes"] + "\n证券：" + ", ".join(m["symbols"]) + "\n" + coverage_text(m.get("quality"))
                                   + "\n" + rules_summary(m["rules"])
                                   + "\nSHA256: " + m["sha256"])
            else:
                notes.setPlainText('请先选择一行数据，再检查缺口、编辑规则或使用所选数据。')
        grid.itemSelectionChanged.connect(selected)
        actions = QtWidgets.QHBoxLayout()
        actions.addWidget(help_target(button("下载历史行情", lambda: (dialog.accept(), self.download_dialog())), 'window.MainWindow.open_data_center.button'))
        cancel_download = help_target(button("取消下载", lambda: (self.cancel_download(), dialog.accept())), 'window.MainWindow.open_data_center.cancel_download')
        cancel_download.setEnabled(bool(self.history_process and self.history_process.is_alive()))
        cancel_download.setToolTip('停止当前历史数据下载。' if cancel_download.isEnabled() else '当前没有正在运行的历史数据下载任务。')
        actions.addWidget(cancel_download)
        actions.addWidget(help_target(button("导入数据包", lambda: (dialog.accept(), self.import_dataset())), 'window.MainWindow.open_data_center.button2'))
        actions.addWidget(help_target(button("恢复未完成录制", lambda: (dialog.accept(), self.recover_recordings())), 'window.MainWindow.open_data_center.button3'))
        def inspect():
            i = selected_index()
            if i >= 0:
                dialog.accept()
                self.open_quality(datasets[i]["id"])
        check = help_target(button("检查缺口", inspect), 'window.MainWindow.open_data_center.check')
        check.setEnabled(False)
        grid.itemSelectionChanged.connect(lambda: check.setEnabled(selected_index() >= 0))
        inspection_actions = QtWidgets.QHBoxLayout()
        inspection_actions.addWidget(check)
        def edit_rules():
            i = selected_index()
            if i >= 0:
                dialog.accept()
                self.open_rule_history(datasets[i]["id"])
        rules_button = help_target(button("证券规则", edit_rules), 'window.MainWindow.open_data_center.rules_button')
        rules_button.setEnabled(False)
        grid.itemSelectionChanged.connect(lambda: rules_button.setEnabled(selected_index() >= 0))
        inspection_actions.addWidget(rules_button)
        inspection_actions.addStretch()
        def use():
            i = selected_index()
            if i >= 0:
                self.dataset_combo.setCurrentIndex(self.dataset_combo.findData(datasets[i]["id"]))
                self.dataset_changed()
                dialog.accept()
        use_button = help_target(button("使用所选数据", use, True), 'window.MainWindow.open_data_center.button4')
        use_button.setToolTip('先在上方表格选择一行数据。')
        grid.itemSelectionChanged.connect(lambda: use_button.setEnabled(selected_index() >= 0))
        inspection_actions.addWidget(use_button)
        selected()
        for control in (check, rules_button, use_button):
            control.setEnabled(selected_index() >= 0)
        layout.addLayout(actions)
        layout.addLayout(inspection_actions)
        dialog.exec()

    def open_rule_history(self, identity):
        from astock.rule_history_ui import RuleHistoryDialog
        dialog = RuleHistoryDialog(self.root, identity, self)
        screen = self.screen().availableGeometry()
        dialog.resize(min(1040, screen.width() - 40), min(620, screen.height() - 60))
        dialog.exec()
        if dialog.saved_id:
            self.refresh_library()
            self.dataset_combo.setCurrentIndex(self.dataset_combo.findData(dialog.saved_id))
            self.dataset_changed()
            self.statusBar().showMessage("规则已另存为新数据版本，原数据及已有回测保留", 8000)
        dialog.deleteLater()

    def open_quality(self, identity):
        from astock.quality_ui import QualityDialog
        dialog = QualityDialog(self.root, identity, self)
        screen = self.screen().availableGeometry()
        dialog.resize(min(1020, screen.width() - 40), min(620, screen.height() - 60))
        dialog.exec()
        dialog.deleteLater()

    def download_dialog(self):
        if self.history_process and self.history_process.is_alive():
            self.error("已有历史下载任务正在运行")
            return
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("下载历史行情")
        available = self.screen().availableGeometry()
        dialog.setMinimumWidth(min(580, available.width() - 40))
        form = QtWidgets.QFormLayout(dialog)
        symbols = help_target(QtWidgets.QLineEdit("510300.SH"), 'window.MainWindow.download_dialog.symbols')
        symbols.setObjectName("historySymbols")
        period = help_target(QtWidgets.QComboBox(), 'window.MainWindow.download_dialog.period')
        period.setObjectName("historyPeriod")
        for name, value in (("日线", "1d"), ("1 分钟", "1m"), ("5 分钟", "5m"), ("15 分钟", "15m"), ("30 分钟", "30m"), ("60 分钟", "60m")):
            period.addItem(name, value)
        source = help_target(QtWidgets.QComboBox(), 'window.MainWindow.download_dialog.source')
        source.setObjectName("historySource")
        source.addItem("腾讯 · 日线", "tencent")
        current = now_cn()
        today = QtCore.QDate(current.year, current.month, current.day)
        default_start = today.addDays(-89)
        start = help_target(QtWidgets.QDateEdit(default_start), 'window.MainWindow.download_dialog.start')
        end = help_target(QtWidgets.QDateEdit(today), 'window.MainWindow.download_dialog.end')
        start.setObjectName("historyStart")
        end.setObjectName("historyEnd")
        for w in (start, end):
            w.setCalendarPopup(True)
            w.setDisplayFormat("yyyy-MM-dd")
        form.addRow("证券代码", symbols)
        symbol_presets = QtWidgets.QHBoxLayout()
        for name, codes, identity in (
            ("宽基 ETF 三只", "510300.SH,510500.SH,159915.SZ", "historyPresetEtf"),
            ("沪深股票三只", "600000.SH,000001.SZ,600036.SH", "historyPresetStocks"),
        ):
            preset = help_target(button(name, lambda checked=False, value=codes: symbols.setText(value)), 'window.MainWindow.download_dialog.preset')
            preset.setObjectName(identity)
            preset.setToolTip("填入一组练习代码，可继续修改；不代表推荐投资，也不保证所选区间无权益事件。")
            symbol_presets.addWidget(preset)
        form.addRow("练习组合", symbol_presets)
        form.addRow("周期", period)
        form.addRow("来源", source)
        form.addRow("开始", start)
        form.addRow("结束", end)
        range_presets = QtWidgets.QHBoxLayout()
        def set_recent_range(days):
            start.setDate(today.addDays(-(days - 1)))
            end.setDate(today)
        for days in (30, 90, 365):
            preset = help_target(button(f"最近 {days} 天", lambda checked=False, value=days: set_recent_range(value)), 'window.MainWindow.download_dialog.preset2')
            preset.setObjectName(f"historyRecent{days}")
            preset.setToolTip("按北京时间今天向前选择日历日期；实际返回交易日范围以数据源为准。")
            range_presets.addWidget(preset)
        form.addRow("快捷日期", range_presets)
        daily_hint = ("日线使用腾讯公开历史行情，默认最近 90 个日历日。下载后会检查权益事件与实际覆盖范围。\n"
                      "下载成功不等于可回测：区间内若有尚未补齐的分红送转资料，仍需完成权益核对。")
        hint = label(daily_hint, "muted", True)
        hint.setObjectName("historyHint")
        hint.setMinimumHeight(hint.fontMetrics().height() * 4)
        form.addRow(hint)
        def change_period():
            source.clear()
            if period.currentData() == "1d":
                source.addItem("腾讯 · 日线", "tencent")
                hint.setText(daily_hint)
            else:
                from astock.minute_history import SOURCES
                for value, text in SOURCES.items():
                    source.addItem(text, value)
                hint.setText("分钟接口只返回近期窗口。新浪当前适配器最多请求 1,970 根；东方财富 1 分钟通常近 5 个交易日。\n"
                             "实际范围以返回值为准；软件会核对昨收参考和权益事件，不会补造缺失行情。")
                if start.date() == default_start and end.date() == today:
                    start.setDate(end.date().addDays(-7))
            dialog.adjustSize()
        period.currentIndexChanged.connect(change_period)
        def download():
            try:
                codes = [symbol_code(s) for s in re.split(r"[,，\s]+", symbols.text()) if s]
                if not 1 <= len(codes) <= 20 or start.date() > end.date():
                    raise ValueError("检查证券数量和日期范围")
                self.history_process = self.ctx.Process(target=download_history_worker,
                    args=(self.output, str(self.root), codes, period.currentData(), start.date().toString("yyyy-MM-dd"),
                          end.date().toString("yyyy-MM-dd"), source.currentData()), name="AStockHistory", daemon=True)
                self.history_process.start()
                self.statusBar().showMessage("正在后台下载历史数据，界面可继续使用…")
                dialog.accept()
            except Exception as e:
                self.error(str(e))
        download_button = help_target(button("开始下载", download, True), 'window.MainWindow.download_dialog.download_button')
        download_button.setObjectName("historyDownload")
        form.addRow(download_button)
        dialog.exec()

    def cancel_download(self):
        if self.history_process and self.history_process.is_alive():
            self.history_process.terminate()
            self.history_process.join(1)
            self.statusBar().showMessage("历史下载已取消；已有完整数据集保持不变", 6000)

    def import_dataset(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择 AStock 数据包元数据（同目录须有 Parquet）", "", "元数据 (*.json)")
        if not path:
            return
        self.start_import(path)

    def start_import(self, path):
        try:
            self.import_token = self.data_jobs.start("import", source=str(path))
            self.cancel_import_button.show()
            self.statusBar().showMessage("正在后台复制和校验数据，可继续使用工作台…")
        except Exception as e:
            self.error(str(e))

    def recover_recordings(self):
        self.show_operation("recover")

    def export_current(self):
        self.switch_workspace(4)
        self.home_accounts.selector.setFocus()
        self.statusBar().showMessage('请选择历史记录，核对策略和账户后点击“导出所选报告”。', 7000)

    def compare_runs(self):
        self.show_operation("compare")

    def show_operation(self, kind, identity=None, name=""):
        from astock.operations_ui import OperationDialog
        key = (kind, identity)
        dialog = self.operations.get(key)
        if dialog is None:
            dialog = OperationDialog(self.root, kind, identity, name, self)
            self.operations[key] = dialog
            dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.finished.connect(lambda _: self.operations.pop(key, None))
            dialog.view_run.connect(self.view_saved_run)
            dialog.view_dataset.connect(self.view_recorded_data)
            dialog.data_changed.connect(lambda: self.refresh_library() if not self.closing else None)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def view_saved_run(self, identity):
        if not self.select_run(identity) and self.learning.run_id == identity:
            # Legacy practice may receive its account id before the first saved snapshot.
            destination = 2 if self.learning.lesson == 3 and self.learning.route != 'offline' else 1
            self.workspace_run_ids[destination] = identity
            self.active_id = identity
            self.clear_execution_tables()
            self.switch_workspace(destination)
            self.engine_commands.put({'op': 'load', 'id': identity})
        self.raise_()
        self.activateWindow()

    def view_recorded_data(self, identity):
        self.refresh_library()
        self.dataset_combo.setCurrentIndex(self.dataset_combo.findData(identity))
        self.mode_combo.setCurrentIndex(self.mode_combo.findData("replay"))
        self.switch_workspace(0)
        self.raise_()
        self.activateWindow()

    def error(self, message, popup=True):
        self.log_view.appendPlainText("错误  " + message)
        self.statusBar().showMessage(message.splitlines()[-1][:250], 15000)
        self.bottom_tabs.setCurrentIndex(3)
        self.notice_text.setText(message.strip().splitlines()[-1][:300])
        self.notice.show()
        if popup:
            QtWidgets.QMessageBox.warning(self, "需要处理", message[:2500])

    def closeEvent(self, event):
        if self.closing:
            event.accept()
            return
        self.closing = True
        self.help_controller.close()
        from shiboken6 import isValid
        for name in ('control_tour', 'task_guide', 'onboarding_dialog'):
            if hasattr(self, name) and isValid(getattr(self, name)):
                getattr(self, name).close()
        for dialog in self.findChildren(QtWidgets.QDialog):
            if getattr(dialog, 'instruction_preview', False):
                dialog.close()
        self.course_library.shutdown()
        if hasattr(self, "strategy_dialog"):
            self.strategy_dialog.close()
        self.restore_learning_layout()
        if self.analysis_layout is not None:
            self.toggle_analysis_layout()
        for dialog in list(self.operations.values()):
            dialog.close()
        self.poll_timer.stop()
        self.freshness_timer.stop()
        self.data_jobs.close()
        self.save_strategy(quiet=True)
        try:
            self.store.set_setting("watchlist", ",".join(self.symbols()))
        except ValueError:
            pass  # Keep the last valid watchlist if an unfinished edit is invalid.
        self.store.set_setting("layout", bytes(self.saveState().toBase64()).decode())
        if self.processes:
            self.market_commands.put({"op": "shutdown"})
            self.engine_commands.put({"op": "shutdown"})
        for process in self.processes:
            process.join(3)
            if process.is_alive():
                process.terminate()
                process.join(1)
        if self.history_process and self.history_process.is_alive():
            self.history_process.terminate()
            self.history_process.join(1)
        # A closed window no longer consumes messages. Release all queues it owns,
        # including queues temporarily replaced by an integration, and never wait
        # for a producer whose consumer was stopped above.
        for channel in self._ipc_queues:
            channel.close()
            channel.cancel_join_thread()
        self.store.close()
        event.accept()
