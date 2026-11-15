"""Integrated QMT-oriented navigation and migration course widgets."""
from astock.help_registry import help_target
from PySide6 import QtCore, QtWidgets

from astock.qmt_learning import COURSES, SOURCES
from astock.ui_components import button, label, table


class MigrationCourse(QtWidgets.QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.progress = window.store.setting("qmt_course_v1", {})
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(label("QMT 迁移课 · 知识自测与四课实作分别记录", "muted", True))
        self.selector = help_target(QtWidgets.QComboBox(), 'qmt_workspace.MigrationCourse.__init__.selector')
        self.selector.addItems([course["title"] for course in COURSES])
        layout.addWidget(self.selector)
        self.body = help_target(QtWidgets.QTextBrowser(), 'qmt_workspace.MigrationCourse.__init__.body')
        self.body.setOpenExternalLinks(True)
        layout.addWidget(self.body, 1)
        self.question = label("", wrap=True)
        layout.addWidget(self.question)
        self.answers = help_target(QtWidgets.QComboBox(), 'qmt_workspace.MigrationCourse.__init__.answers')
        layout.addWidget(self.answers)
        row = QtWidgets.QHBoxLayout()
        self.jump = help_target(button("打开练习入口", self.navigate), 'qmt_workspace.MigrationCourse.__init__.jump')
        row.addWidget(self.jump)
        row.addWidget(help_target(button("检查答案", self.check), 'qmt_workspace.MigrationCourse.__init__.button'))
        row.addWidget(help_target(button("下一课", self.next_course), 'qmt_workspace.MigrationCourse.__init__.button2'))
        layout.addLayout(row)
        self.feedback = label("", "muted", True)
        layout.addWidget(self.feedback)
        self.selector.currentIndexChanged.connect(self.render)
        self.render()

    def render(self, *_):
        course = COURSES[self.selector.currentIndex()]
        links = " · ".join(f'<a href="{url}">{title}</a>' for title, url in SOURCES)
        self.body.setHtml(course["body"] + "<p>官方参考：" + links + "</p>")
        self.question.setText(course["question"])
        self.answers.clear()
        self.answers.addItem("请选择答案", -1)
        for index, text in enumerate(course["choices"]):
            self.answers.addItem(text, index)
        self.jump.setText(course["target"])
        count = sum(bool(self.progress.get(c["id"])) for c in COURSES)
        self.feedback.setText(f"知识自测 {count}/{len(COURSES)} 通过 · 本课"
                              + ("已通过，可重复练习" if self.progress.get(course["id"]) else "尚未通过"))

    def check(self):
        course = COURSES[self.selector.currentIndex()]
        answer = self.answers.currentData()
        if answer == -1:
            self.feedback.setText("请先选择一个答案。")
        elif answer == course["answer"]:
            self.progress[course["id"]] = True
            self.window.store.set_setting("qmt_course_v1", self.progress)
            count = sum(bool(self.progress.get(c["id"])) for c in COURSES)
            self.feedback.setText(f"回答正确 · 已通过 {count}/{len(COURSES)} 课。请打开对应入口动手练习。")
        else:
            self.feedback.setText("还不正确。请重读本课的操作区别，再选择答案。")

    def next_course(self):
        self.selector.setCurrentIndex(min(self.selector.currentIndex() + 1, len(COURSES) - 1))

    def navigate(self):
        w = self.window
        action = COURSES[self.selector.currentIndex()]["action"]
        actions = {"home": lambda: w.switch_workspace(4), "data": w.open_data_center,
                   "research": lambda: w.switch_workspace(0), "setup": w.configure_backtest,
                   "results": lambda: w.switch_workspace(1), "trading": lambda: w.switch_workspace(2),
                   "api": w.show_api, "practice": lambda: w.learning_sections.setCurrentIndex(0)}
        actions[action]()


def build_home(window):
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.addWidget(label("账户与记录", "title"))
    layout.addWidget(label("查看本地虚拟账户、持仓、委托与历史运行。写策略、回测和数据入口统一在左侧。", "muted", True))
    from astock.account_overview import AccountOverview
    window.home_accounts = AccountOverview(window)
    layout.addWidget(window.home_accounts, 1)
    window.pages.addWidget(page)


def build_market(window):
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)
    row = QtWidgets.QHBoxLayout()
    row.addWidget(label("数据中心 · 历史数据与实时行情", "title"))
    row.addStretch()
    row.addWidget(help_target(button("证券搜索 / 添加自选", window.open_catalog), 'qmt_workspace.build_market.button'))
    row.addWidget(help_target(button("管理历史数据 / 下载 / 导入", window.open_data_center), 'qmt_workspace.build_market.button2'))
    layout.addLayout(row)
    window.data_market_tabs = help_target(QtWidgets.QTabWidget(), 'qmt_workspace.build_market.data_market_tabs')
    layout.addWidget(window.data_market_tabs, 1)
    history = QtWidgets.QWidget()
    historical_layout = QtWidgets.QVBoxLayout(history)
    historical_layout.addWidget(label("选择一份历史数据用于回测。教学数据可直接练习；下载或导入真实数据时先核对来源、覆盖范围和复权说明。", "muted", True))
    window.data_overview_table = help_target(table(["名称", "数据类型", "来源", "起始", "结束", "记录数"]), 'qmt_workspace.build_market.data_overview_table')
    window.data_overview_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    historical_layout.addWidget(window.data_overview_table, 1)
    window.data_selection_note = label("", "muted", True)
    historical_layout.addWidget(window.data_selection_note)
    history_actions = QtWidgets.QHBoxLayout()
    history_actions.addWidget(help_target(button("刷新数据列表", lambda: (window.refresh_library(), refresh_data_overview(window))), 'qmt_workspace.build_market.refresh_data'))
    history_actions.addWidget(help_target(button("去写策略", lambda: window.switch_workspace(0)), 'qmt_workspace.build_market.write_strategy'))
    history_actions.addWidget(help_target(button("去历史回测", lambda: window.switch_workspace(1), True), 'qmt_workspace.build_market.backtest'))
    history_actions.addStretch()
    historical_layout.addLayout(history_actions)

    def choose_data():
        item = window.data_overview_table.item(window.data_overview_table.currentRow(), 0)
        if item is not None:
            dataset = item.data(QtCore.Qt.ItemDataRole.UserRole)
            window.dataset_combo.setCurrentIndex(window.dataset_combo.findData(dataset))
            window.data_selection_note.setText("已选择：" + item.text() + "。这里只选择数据，前往历史回测后再设置区间并开始运行。")

    window.data_overview_table.itemSelectionChanged.connect(choose_data)
    window.data_market_tabs.addTab(history, "历史数据")
    market = QtWidgets.QWidget()
    window.data_market_tabs.addTab(market, "实时行情")
    layout = QtWidgets.QVBoxLayout(market)
    window.market_overview_status = label("未连接 · 添加自选后连接行情", "muted", True)
    layout.addWidget(window.market_overview_status)
    row = QtWidgets.QHBoxLayout()
    row.addWidget(help_target(button("连接 / 断开行情", window.toggle_market), 'qmt_workspace.build_market.button3'))
    row.addWidget(help_target(button("查看订阅标的", lambda: window.parameter_dock.show()), 'qmt_workspace.build_market.button4'))
    row.addWidget(help_target(button("去模拟交易", lambda: window.switch_workspace(2)), 'qmt_workspace.build_market.button5'))
    row.addStretch()
    layout.addLayout(row)
    window.market_overview_table = help_target(table(["代码 / 名称", "最新", "买一", "卖一", "行情时间", "年龄 / 秒"]), 'qmt_workspace.build_market.window.market_overview_table')
    layout.addWidget(window.market_overview_table, 1)
    layout.addWidget(label("先用“管理历史数据 / 下载 / 导入”准备回测数据。下方报价与模拟交易共用行情连接；"
                           "连接报价不会自动下载历史数据。", "muted", True))
    window.pages.addWidget(page)


def refresh_data_overview(window):
    from astock.data_identity import display_name, origin_label, source_summary
    selected = window.dataset_combo.currentData()
    grid = window.data_overview_table
    blocker = QtCore.QSignalBlocker(grid)
    grid.clearContents()
    grid.setRowCount(len(window.datasets))
    for row, meta in enumerate(window.datasets):
        values = [display_name(meta), 'K 线' if meta['kind'] == 'bar' else '报价快照',
                  origin_label(meta) + ' · ' + meta.get('source', '未注明'),
                  meta.get('start', '')[:16], meta.get('end', '')[:16], str(meta.get('count', 0))]
        for column, value in enumerate(values):
            grid.setItem(row, column, QtWidgets.QTableWidgetItem(value))
        grid.item(row, 0).setData(QtCore.Qt.ItemDataRole.UserRole, meta['id'])
        grid.item(row, 0).setToolTip(source_summary(meta))
        if meta['id'] == selected:
            grid.selectRow(row)
            window.data_selection_note.setText("当前回测数据：" + display_name(meta) + "。更换数据后请重新核对回测区间。")
    del blocker


def name_model(window, copy=True):
    name, ok = QtWidgets.QInputDialog.getText(window, "另存策略副本" if copy else "新建策略", "策略名称")
    name = name.strip()
    if not ok or not name:
        return
    from astock.strategy import TEMPLATES
    if name == window.current_template or name in TEMPLATES or any(s["name"] == name for s in window.store.strategies()):
        window.error("名称已存在，请为新策略使用不同名称。")
        return
    window.save_strategy(quiet=True)
    window.current_template = name
    window.strategy_title.setText(name)
    if not copy:
        window.editor.setPlainText('''from astock.strategy import Strategy

PARAMETERS = {}


class UserStrategy(Strategy):
    def initialize(self, ctx):
        ctx.explain("模型初始化：先观察数据，再编写交易条件")

    def on_bar(self, ctx, bar):
        pass
''')
        window.rebuild_parameters()
    window.strategy_description.setText("本地 Python 策略 · 使用 AStock 接口；编辑完成后到历史回测选择数据并运行")
    window.save_strategy()
    window.switch_workspace(0)


def export_model(window):
    from pathlib import Path
    path, _ = QtWidgets.QFileDialog.getSaveFileName(window, "导出 AStock Python 模型", "model.py", "Python (*.py)")
    if path:
        try:
            Path(path).write_text(window.editor.toPlainText(), encoding="utf-8")
            window.statusBar().showMessage("模型已导出为 UTF-8 Python 源码（AStock 接口）", 6000)
        except OSError as error:
            window.error(str(error))
