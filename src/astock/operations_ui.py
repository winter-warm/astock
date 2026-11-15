"""Modeless operations keep a fixed target while the user explores other accounts."""
from astock.help_registry import help_target
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from astock.data_jobs import DataJobs
from astock.report_jobs import publish_report
from astock.ui_components import RecordTable, button, label


def comparison_row(row):
    from astock.window import MODES, STATUS
    stats = row["statistics"]
    return [row["name"] + " / " + row["id"][:6], STATUS.get(row["status"], row["status"]),
            MODES.get(row["mode"], row["mode"]), row["dataset"],
            "—" if row["error"] else f"{stats['return']:+.2%}",
            "—" if row["error"] else f"{stats['max_drawdown']:.2%}",
            "—" if row["error"] else f"{stats['fees']:.2f}",
            "—" if row["error"] else stats["trades"], row["basis"][:8]]


class OperationDialog(QtWidgets.QDialog):
    view_run = QtCore.Signal(str)
    view_dataset = QtCore.Signal(str)
    data_changed = QtCore.Signal()

    def __init__(self, root, kind, identity=None, name="", parent=None, *, instruction_preview=False):
        super().__init__(parent)
        self.instruction_preview = instruction_preview
        self.root, self.kind, self.identity = Path(root), kind, identity
        self.token = self.report_path = self.result = None
        self.jobs = DataJobs(self.root / "datasets", self)
        self.jobs.message.connect(self.receive)
        self.jobs.settled.connect(lambda settled: self.data_changed.emit() if settled == "recover" else None)
        self.setWindowTitle({"report": "导出运行报告", "compare": "独立运行对比", "recover": "整理录制行情"}[kind])
        self.resize(760 if kind == "report" else 1100, 310 if kind == "report" else 600)
        layout = QtWidgets.QVBoxLayout(self)
        title = label((name + " / " + (identity or '未选账户')[:6]) if kind == "report" else
                      "查看已保存的运行结果" if kind == "compare" else "整理已停止或中断的录制", "title", True)
        title.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        layout.addWidget(title)
        self.note = label("导出以后台读取时的已保存快照为准，账户可以继续运行。每次导出单独保存。"
                          if kind == "report" else "数据、撮合费用、交易规则、本金、引擎版本及观察时刻共同组成比较依据。"
                          "依据相同也需要核对运行是否完成、策略及人工操作。", "muted", True)
        layout.addWidget(self.note)
        if kind == "recover":
            self.note.setText("正在使用的录制会跳过。按目录逐个保存；取消会保留已完成数据及原始分块，未完成目录可再次整理。")
        self.summary = label("准备读取…", "badge", True)
        self.summary.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.table = None
        if kind == "compare":
            self.table = help_target(RecordTable(["运行", "状态", "模式", "数据", "收益", "最大回撤", "费用", "成交数", "比较依据"],
                                     comparison_row, [180, 90, 90, 170, 90, 90, 90, 70, 90]), 'operations_ui.OperationDialog.__init__.table')
            self.table.itemSelectionChanged.connect(self.select_row)
            layout.addWidget(self.table, 1)
        elif kind == "recover":
            self.table = help_target(RecordTable(["录制目录", "状态", "记录数", "说明"],
                                     lambda row: [row["directory"], row["status"], row["count"], row["message"]],
                                     [230, 100, 100, 450]), 'operations_ui.OperationDialog.__init__.table2')
            self.table.itemSelectionChanged.connect(self.select_row)
            layout.addWidget(self.table, 1)
        self.detail = label("", "muted", True)
        self.detail.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.detail.setMinimumHeight(self.detail.fontMetrics().lineSpacing() * 3)
        self.detail.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.detail)
        actions = QtWidgets.QHBoxLayout()
        self.retry = help_target(button({"report": "重新导出", "compare": "刷新对比", "recover": "重新整理"}[kind], self.start), 'operations_ui.OperationDialog.__init__.retry')
        self.cancel_button = help_target(button("取消", self.cancel), 'operations_ui.OperationDialog.__init__.cancel_button')
        self.open_button = help_target(button({"report": "打开报告", "compare": "查看选中运行", "recover": "选择此数据"}[kind], self.open_result), 'operations_ui.OperationDialog.__init__.open_button')
        self.open_button.setEnabled(False)
        for widget in (self.retry, self.cancel_button, self.open_button):
            actions.addWidget(widget)
        actions.addStretch()
        actions.addWidget(help_target(button("关闭", self.close), 'operations_ui.OperationDialog.__init__.button'))
        layout.addLayout(actions)
        if instruction_preview:
            self.setWindowTitle(self.windowTitle() + ' · 讲解预览')
            self.summary.setText('讲解预览：不会开始后台任务，不会导出报告或整理录制。关闭后从原入口开始实作。')
            self.progress.hide()
            self.retry.setEnabled(False)
            self.cancel_button.setEnabled(False)
        else:
            self.start()

    def start(self):
        if self.instruction_preview:
            return
        self.report_path = self.result = None
        self.detail.clear()
        self.open_button.setEnabled(False)
        if self.table:
            self.table.set_records([], None)
        self.summary.setText("正在后台检查录制目录…" if self.kind == "recover" else "正在后台读取已保存的运行…")
        self.progress.setRange(0, 0)
        self.progress.show()
        try:
            self.token = self.jobs.start(self.kind, root=str(self.root), identity=self.identity)
            self.retry.setEnabled(False)
            self.cancel_button.setEnabled(True)
        except Exception as error:
            self.summary.setText("无法开始：" + str(error))
            self.finish_controls()

    def finish_controls(self):
        self.token = None
        self.retry.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress.hide()

    def cancel(self):
        if self.token is None:
            return
        self.jobs.cancel(self.kind)
        self.finish_controls()
        self.summary.setText("已取消；已完成的数据和原始分块保留，可再次整理。" if self.kind == "recover"
                             else "已取消；已有报告和运行记录保留。")

    def receive(self, message):
        if self.token is None or message["token"] != self.token:
            return
        if message["type"] == "progress":
            self.summary.setText(message["phase"] + (f" · {message['done']:,}" if message.get("done") else ""))
            total = message.get("total", 0)
            self.progress.setRange(0, total)
            self.progress.setValue(message.get("done", 0))
            return
        self.finish_controls()
        if message["type"] == "error":
            self.summary.setText("操作失败：" + message["message"])
            return
        self.result = message["result"]
        if self.kind == "report":
            try:
                self.report_path = publish_report(self.root, message["request"], self.result)
                self.summary.setText(f"报告已保存 · {self.result['trades']:,} 笔成交")
                snapshot = self.result["snapshot"]
                self.detail.setText(f"观察截至：{snapshot['observed_until'] or '尚无行情'}\n{self.report_path.parent}")
                self.open_button.setEnabled(True)
            except (OSError, ValueError) as error:
                self.summary.setText("报告保存失败：" + str(error))
        elif self.kind == "compare":
            self.table.set_records(self.result["rows"], str(self.result["read_at"]))
            self.summary.setText(f"{len(self.result['rows']):,} 个运行 · {self.result['basis_groups']} 组依据 · "
                                 f"{self.result['errors']} 条记录需要处理")
            self.detail.setText("读取时间：" + self.result["read_at"].strftime("%m-%d %H:%M:%S") +
                                "。点击一行查看详情；不同依据的收益不宜直接比较。")
        else:
            self.table.set_records(self.result["rows"], self.identity)
            self.summary.setText(f"完成 {self.result['completed']} 个 · 正在使用 {self.result['busy']} 个 · "
                                 f"需要处理 {self.result['errors']} 个")
            self.detail.setText("点击一行查看说明。原始录制分块均保留；再次整理不会重复生成已完成的数据。")
            self.data_changed.emit()

    def select_row(self):
        row = self.table.current_record()
        if self.kind == "recover":
            self.open_button.setEnabled(bool(row and row["dataset"]))
            if row:
                self.detail.setText(row["directory"] + "：" + row["message"])
            return
        self.open_button.setEnabled(bool(row and not row["error"]))
        if row:
            self.detail.setText(row["error"] or f"{row['name']} / {row['id']} · 创建于 {row['created']}\n"
                                f"比较依据 {row['basis'][:8]}。表中为已保存快照，正在运行的账户请刷新后查看。")

    def open_result(self):
        if self.kind == "report" and self.report_path:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.report_path)))
        elif self.table:
            row = self.table.current_record()
            if self.kind == "recover" and row and row["dataset"]:
                self.view_dataset.emit(row["dataset"])
            elif self.kind == "compare" and row and not row["error"]:
                self.view_run.emit(row["id"])

    def done(self, result):
        self.cancel()
        self.jobs.close()
        super().done(result)

    def closeEvent(self, event):
        self.cancel()
        self.jobs.close()
        super().closeEvent(event)
