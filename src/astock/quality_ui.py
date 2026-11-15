from astock.help_registry import help_target
from PySide6 import QtCore, QtGui, QtWidgets

from astock.data_jobs import DataJobs
from astock.data_quality import LABELS, coverage_text, publish_coverage
from astock.ui_components import RecordTable, button, label


class QualityDialog(QtWidgets.QDialog):
    def __init__(self, root, identity, parent=None, *, instruction_preview=False):
        super().__init__(parent)
        self.instruction_preview = instruction_preview
        self.root, self.identity = root, identity
        self.token = self.report = self.report_path = None
        self.jobs = DataJobs(root / "datasets", self)
        self.jobs.message.connect(self.receive)
        self.setWindowTitle("数据覆盖检查 · 交易日与分钟缺口")
        self.resize(1020, 620)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(label("核对实际覆盖范围", "title"))
        self.summary = label("准备检查…", "badge", True)
        self.summary.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        self.explanation = label("后台读取原始记录；不会补齐、改价或改变运行中的账户。", "muted", True)
        self.explanation.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        layout.addWidget(self.explanation)
        self.table = help_target(RecordTable(["类型", "证券", "起始时刻", "结束时刻", "数量"],
            lambda row: [LABELS[row["kind"]], row["symbol"], row["start"].replace("T", " "),
                         row["end"].replace("T", " "), f"{row['count']:,} {row['unit']}"], [150, 110, 245, 245, 120]), 'quality_ui.QualityDialog.__init__.table')
        layout.addWidget(self.table, 1)
        self.detail = label("", "muted", True)
        self.detail.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.detail.setMaximumHeight(90)
        layout.addWidget(self.detail)
        actions = QtWidgets.QHBoxLayout()
        self.retry = help_target(button("重新检查", self.start), 'quality_ui.QualityDialog.__init__.retry')
        self.cancel_button = help_target(button("取消检查", self.cancel), 'quality_ui.QualityDialog.__init__.cancel_button')
        self.open_button = help_target(button("打开完整检查报告", self.open_report), 'quality_ui.QualityDialog.__init__.open_button')
        self.open_button.setEnabled(False)
        actions.addWidget(self.retry)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.open_button)
        actions.addStretch()
        actions.addWidget(help_target(button("关闭", self.close), 'quality_ui.QualityDialog.__init__.button'))
        layout.addLayout(actions)
        self.table.itemSelectionChanged.connect(self.show_detail)
        if instruction_preview:
            self.setWindowTitle(self.windowTitle() + ' · 讲解预览')
            self.summary.setText('讲解预览：不会读取或检查数据，不会保存报告。关闭后从数据中心开始实际检查。')
            self.retry.setEnabled(False)
            self.cancel_button.setEnabled(False)
        else:
            self.start()

    def start(self):
        if self.instruction_preview:
            return
        self.report = self.report_path = None
        self.open_button.setEnabled(False)
        self.table.set_records([], self.identity)
        self.summary.setText("正在核对文件与交易日历…")
        self.detail.clear()
        try:
            self.token = self.jobs.start("quality", root=str(self.root / "datasets"), identity=self.identity)
            self.retry.setEnabled(False)
            self.cancel_button.setEnabled(True)
        except Exception as error:
            self.summary.setText("无法开始检查：" + str(error))

    def cancel(self):
        self.jobs.cancel("quality")
        self.token = None
        self.retry.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.summary.setText("检查已取消；原始数据保持不变。")

    def receive(self, message):
        if self.token is None or message["token"] != self.token:
            return
        if message["type"] == "progress":
            self.summary.setText(message["phase"] + f" · 已读 {message.get('done', 0):,} 条")
            return
        self.token = None
        self.retry.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if message["type"] == "error":
            self.summary.setText("检查失败：" + message["message"])
            return
        self.report = message["result"]
        self.summary.setText(coverage_text(self.report))
        self.explanation.setText(self.report["note"] + "\n检查依据：" + self.report["basis"] + "；"
                                 + self.report.get("start", "") + " 至 " + self.report.get("end", ""))
        self.table.set_records(self.report["details"], self.identity)
        self.detail.setText(f"共 {len(self.report['details']):,} 处明细。时间为 K 线结束时刻，连续缺口合并显示；点击一行查看说明。")
        try:
            self.report_path = publish_coverage(self.root, message["request"], self.report)
            self.open_button.setEnabled(True)
        except OSError as error:
            self.detail.setText("检查结果可查看，但报告保存失败：" + str(error))

    def show_detail(self):
        row = self.table.current_record()
        if not row:
            return
        notes = {
            "missing_day": "该交易日未找到此证券的记录。须核对停牌、上市日期或下载窗口，不能仅凭缺失认定是行情错误。",
            "missing_bar": "区间内缺少应有周期的柱，可能是无成交、停牌或来源漏数。软件保留原始时刻，指标不会把缺口填成重复价格。",
            "before_coverage": "请求范围早于此证券实际返回的第一条记录；上游可能只提供近期窗口，也可能尚未上市。",
            "after_coverage": "请求范围晚于此证券实际返回的最后记录；可能尚未收市、停牌或上游未覆盖。",
            "outside_session": "此柱覆盖午休、集合竞价，或未对齐周期。保留供查看，撮合与策略回调会跳过。",
            "closed_day": "交易所日历显示该日休市，真实行情包中的此类 K 线会阻止回测，需核对时间或数据来源。",
            "unknown_calendar": "当前已核对的交易日历为 2023—2026 年；范围之外不把工作日自动认作交易日。",
            "suspended": "数据提供方已将此记录标为停牌；不参与撮合，不把已提供的停牌记录重复记为数据缺口。",
            "state_suspended": "有来源的证券日期区间确认此日整日停牌。没有价格记录不计为缺口；已有记录也不参与撮合。",
            "unlisted": "证券日期资料确认此日未上市或已摘牌，不要求有交易行情；不会补造价格。",
            "unknown_rule": "日期区间未覆盖此交易日，或资料源未返回该日状态。请在证券规则中补充来源后再回测。",
            "outside_range": "源返回了请求范围之外的记录，需要核对下载窗口。报告同时保留实际起止时间。",
        }
        self.detail.setText(notes[row["kind"]])

    def open_report(self):
        if self.report_path:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.report_path)))

    def done(self, result):
        self.cancel()
        self.jobs.close()
        super().done(result)

    def closeEvent(self, event):
        self.cancel()
        self.jobs.close()
        super().closeEvent(event)
