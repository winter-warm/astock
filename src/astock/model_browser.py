"""Optional strategy picker beside the directly accessible inline editor."""
from astock.help_registry import help_target
from PySide6 import QtCore, QtWidgets

from astock.qmt_workspace import name_model
from astock.strategy import TEMPLATES
from astock.ui_components import button, label, table


class ModelBrowser(QtWidgets.QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addWidget(label("模板与已存策略", "title"))
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setSpacing(4)
        toolbar.addWidget(help_target(button("新建策略", self.new_model), 'model_browser.ModelBrowser.__init__.button'))
        toolbar.addWidget(help_target(button("导入策略", self.import_model), 'model_browser.ModelBrowser.__init__.button2'))
        toolbar.addWidget(help_target(button("刷新", self.refresh), 'model_browser.ModelBrowser.__init__.button3'))
        toolbar.addStretch()
        self.search = help_target(QtWidgets.QLineEdit(), 'model_browser.ModelBrowser.__init__.search')
        self.search.setPlaceholderText("按策略名称筛选")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(280)
        self.search.setAccessibleName("按策略名称筛选")
        toolbar.addWidget(self.search)
        layout.addLayout(toolbar)
        self.models = help_target(table(["名称", "类型", "操作", "说明"]), 'model_browser.ModelBrowser.__init__.models')
        self.models.setObjectName("modelBrowserTable")
        self.models.setAccessibleName("模板与已存策略")
        self.models.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.models.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        header = self.models.horizontalHeader()
        for column, width in ((0, 180), (1, 125), (2, 110)):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeMode.Interactive)
            self.models.setColumnWidth(column, width)
        self.models.verticalHeader().setDefaultSectionSize(28)
        self.models.setMinimumHeight(160)
        layout.addWidget(self.models, 1)
        self.summary = label("", "muted", True)
        layout.addWidget(self.summary)
        layout.addWidget(label("选择“编辑”将策略载入主页面。选择“去回测”先检查数据和设置，再手动开始；"
                               "模板与已保存版本分别列出。", "muted", True))
        self.search.textChanged.connect(self.apply_filter)
        self.models.cellDoubleClicked.connect(lambda row, _column: self.open_row(row))
        self.models.customContextMenuRequested.connect(self.context_menu)
        self.refresh()

    def key_at(self, row):
        item = self.models.item(row, 0)
        return item.data(QtCore.Qt.ItemDataRole.UserRole) if item else None

    def refresh(self):
        selected = self.key_at(self.models.currentRow())
        entries = [("template", name, "Python · 模板", data["description"])
                   for name, data in TEMPLATES.items()]
        entries.extend(("saved", saved["name"], "Python · 已保存",
                        f"本地策略 · 已保存 {len(saved['parameters'])} 项参数")
                       for saved in self.window.store.strategies())
        self.models.setUpdatesEnabled(False)
        try:
            self.models.clearContents()
            self.models.setRowCount(len(entries))
            selected_row = None
            for row, (kind, identity, model_type, description) in enumerate(entries):
                key = (kind, identity)
                name = QtWidgets.QTableWidgetItem(identity)
                name.setData(QtCore.Qt.ItemDataRole.UserRole, key)
                self.models.setItem(row, 0, name)
                self.models.setItem(row, 1, QtWidgets.QTableWidgetItem(model_type))
                self.models.setItem(row, 3, QtWidgets.QTableWidgetItem(description))
                actions = QtWidgets.QWidget()
                action_layout = QtWidgets.QHBoxLayout(actions)
                action_layout.setContentsMargins(2, 0, 2, 0)
                action_layout.setSpacing(2)
                for title, backtest in (("编辑", False), ("去回测", True)):
                    action = help_target(QtWidgets.QToolButton(), 'model_browser.ModelBrowser.refresh.action')
                    action.setText(title)
                    action.setAutoRaise(True)
                    action.setAccessibleName(f"{title} {identity}（{model_type}）")
                    action.clicked.connect(lambda _checked=False, k=key, run=backtest: self.open_key(k, run))
                    action_layout.addWidget(action)
                action_layout.addStretch()
                self.models.setCellWidget(row, 2, actions)
                if key == selected:
                    selected_row = row
            if selected_row is not None:
                self.models.selectRow(selected_row)
            self.apply_filter()
        finally:
            self.models.setUpdatesEnabled(True)

    def apply_filter(self, *_):
        query = self.search.text().strip().casefold()
        visible = []
        for row in range(self.models.rowCount()):
            match = query in self.models.item(row, 0).text().casefold()
            self.models.setRowHidden(row, not match)
            if match:
                visible.append(row)
        if self.models.currentRow() not in visible:
            self.models.clearSelection()
            self.models.setCurrentCell(-1, -1)
            if visible:
                self.models.selectRow(visible[0])
        self.summary.setText(f"显示 {len(visible)} / {self.models.rowCount()} 个策略"
                             + (" · 没有匹配的名称，请修改筛选条件。" if not visible else ""))

    def open_key(self, key, backtest=False):
        for row in range(self.models.rowCount()):
            if self.key_at(row) == key:
                self.models.selectRow(row)
                break
        # Opening can be refused by the window, e.g. if the saved model disappeared.
        opened = self.window.open_strategy_editor(*key)
        if backtest and opened is not False:
            self.window.switch_workspace(1)

    def open_row(self, row, backtest=False):
        key = self.key_at(row)
        if key:
            self.open_key(key, backtest)

    def context_menu(self, position):
        row = self.models.rowAt(position.y())
        if row < 0:
            return
        self.models.selectRow(row)
        key = self.key_at(row)
        menu = QtWidgets.QMenu(self)
        help_target(menu.addAction("编辑策略", lambda: self.open_key(key)), 'model_browser.ModelBrowser.context_menu.addAction')
        help_target(menu.addAction("去历史回测", lambda: self.open_key(key, backtest=True)), 'model_browser.ModelBrowser.context_menu.addAction2')
        menu.exec(self.models.viewport().mapToGlobal(position))

    def new_model(self):
        previous = self.window.current_template
        name_model(self.window, copy=False)
        self.refresh()
        if self.window.current_template != previous:
            self.window.open_strategy_editor()

    def import_model(self):
        self.window.import_strategy()
        self.refresh()
        self.window.open_strategy_editor()
