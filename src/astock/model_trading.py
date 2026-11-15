"""Manage actual local live/manual accounts through the existing execution path."""
from astock.help_registry import help_target
import re

from PySide6 import QtCore, QtWidgets

from astock.domain import symbol_code
from astock.strategy import TEMPLATES, parameter_schema
from astock.ui_components import button, label, populate, table


STATUS = {"RUNNING": "运行中", "PAUSED": "已暂停", "COMPLETED": "已完成", "STOPPED": "已停止",
          "ERROR": "运行异常", "RECOVERED": "恢复 · 未运行", "RECOVERY_ERROR": "恢复核对失败"}
MODES = {"live": "策略仿真", "manual": "手动练习"}


class TradingTasks(QtWidgets.QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        actions = QtWidgets.QHBoxLayout()
        self.create_button = help_target(button("新建策略交易", self.new_task, True), 'model_trading.TradingTasks.__init__.create_button')
        actions.addWidget(self.create_button)
        self.view_button = help_target(button("查看账户", self.view_account), 'model_trading.TradingTasks.__init__.view_button')
        self.view_button.setEnabled(False)
        actions.addWidget(self.view_button)
        actions.addWidget(help_target(button("刷新", self.refresh), 'model_trading.TradingTasks.__init__.button'))
        actions.addStretch()
        layout.addLayout(actions)
        self.accounts = help_target(table(["策略名称", "运行模式", "虚拟账户", "状态"]), 'model_trading.TradingTasks.__init__.accounts')
        self.accounts.setObjectName("modelTradingAccounts")
        self.accounts.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.accounts.itemSelectionChanged.connect(
            lambda: self.view_button.setEnabled(self.selected_id() is not None))
        layout.addWidget(self.accounts, 1)
        self.summary = label("", "muted", True)
        layout.addWidget(self.summary)
        layout.addWidget(label("只列出本地实时仿真和手动账户。选择行不会启动策略；查看账户后，"
                               "可用顶部控制暂停、继续或停止并撤单。历史回测在历史回测页查看；报告和跨运行对比到“账户与记录”。", "muted", True))
        self.refresh()

    def selected_id(self):
        row = self.accounts.currentRow()
        item = self.accounts.item(row, 0) if row >= 0 else None
        return item.data(QtCore.Qt.ItemDataRole.UserRole) if item is not None else None

    def refresh(self):
        selected = self.selected_id()
        scroll = self.accounts.verticalScrollBar().value()
        entries = {entry["id"]: dict(entry) for entry in self.window.store.runs()
                   if entry["mode"] in MODES}
        for identity, state in self.window.states.items():
            if state.get("mode") in MODES:
                entries[identity] = {**entries.get(identity, {}), "id": identity,
                                     "name": state["name"], "mode": state["mode"], "status": state["status"]}
        identities = list(entries)
        rows = [[entry["name"], MODES[entry["mode"]], entry["id"],
                 STATUS.get(entry["status"], entry["status"])] for entry in entries.values()]
        self.accounts.blockSignals(True)
        populate(self.accounts, rows, identities)
        self.accounts.clearSelection()
        self.accounts.setCurrentCell(-1, -1)
        if selected in entries:
            self.accounts.selectRow(identities.index(selected))
        self.accounts.verticalScrollBar().setValue(scroll)
        self.accounts.blockSignals(False)
        self.view_button.setEnabled(self.selected_id() is not None)
        self.summary.setText(f"{len(entries)} 个虚拟账户" if entries else "尚无模型交易账户。连接行情后新建策略交易，或使用下方手动练习。")

    def view_account(self):
        identity = self.selected_id()
        if identity is None:
            return
        self.window.select_run(identity)

    def new_task(self):
        w = self.window
        if w.start_pending:
            w.error("已有账户正在准备，请等待完成或取消准备。")
            return
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("新建策略交易 · 本地仿真")
        dialog.setMinimumWidth(520)
        form = QtWidgets.QFormLayout(dialog)
        model = help_target(QtWidgets.QComboBox(), 'model_trading.TradingTasks.new_task.model')
        model.setObjectName("tradingTaskModel")
        model.addItem("当前编辑模型 · " + w.current_template, ("current", w.current_template))
        for name in TEMPLATES:
            model.addItem("模板 · " + name, ("template", name))
        for strategy in w.store.strategies():
            model.addItem("已保存 · " + strategy["name"], ("saved", strategy["name"]))
        form.addRow("策略模型", model)
        symbols = help_target(QtWidgets.QLineEdit(w.symbol_input.text()), 'model_trading.TradingTasks.new_task.symbols')
        symbols.setObjectName("tradingTaskSymbols")
        form.addRow("证券代码", symbols)
        capital = help_target(QtWidgets.QDoubleSpinBox(), 'model_trading.TradingTasks.new_task.capital')
        capital.setObjectName("tradingTaskCapital")
        capital.setRange(w.capital.minimum(), w.capital.maximum())
        capital.setDecimals(2)
        capital.setValue(w.capital.value())
        form.addRow("初始虚拟资金", capital)
        form.addRow("运行模式", label("本地实时仿真 · 不连接券商交易账户", wrap=True))
        form.addRow(label("证券代码用逗号分隔，最多 20 个。模型使用右侧参数及撮合设置；"
                          "行情订阅包含这些标的后再启动。创建将走现有启动和 ETF 当日规则核对流程，"
                          "成功后建立独立账户。", "muted", True))
        error = label("", "muted", True)
        error.setObjectName("tradingTaskError")
        form.addRow(error)
        buttons = help_target(QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok |
                                            QtWidgets.QDialogButtonBox.StandardButton.Cancel), 'model_trading.TradingTasks.new_task.buttons')
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText("创建并启动仿真")

        def accept():
            try:
                codes = list(dict.fromkeys(symbol_code(s) for s in re.split(r"[,，;；\s]+", symbols.text()) if s))
                if not 1 <= len(codes) <= 20:
                    raise ValueError("请输入 1–20 个有效证券代码。")
                kind, name = model.currentData()
                if kind == "template":
                    code = TEMPLATES[name]["code"]
                elif kind == "current" or name == w.current_template:
                    code = w.editor.toPlainText()
                else:
                    code = next(s["code"] for s in w.store.strategies() if s["name"] == name)
                parameter_schema(code)
            except (ValueError, SyntaxError, TypeError, StopIteration) as exc:
                error.setText(str(exc) or "所选模型已不存在，请重新打开窗口。")
                return
            symbols.setText(",".join(codes))
            dialog.accept()

        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        kind, name = model.currentData()
        w.save_strategy(quiet=True)
        if kind == "template":
            w.load_template(name, save_current=False)
        elif kind == "saved":
            strategy = next(s for s in w.store.strategies() if s["name"] == name)
            w.current_template = name
            w.strategy_title.setText(name)
            w.strategy_description.setText("已保存模型 · 本地 Python 策略")
            w.editor.setPlainText(strategy["code"])
            w.rebuild_parameters(values=strategy["parameters"])
        w.symbol_input.setText(symbols.text())
        w.capital.setValue(capital.value())
        w.switch_workspace(2)
        w.start_live(False)
