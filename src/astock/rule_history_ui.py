from astock.help_registry import help_target
from copy import deepcopy
from datetime import datetime

from PySide6 import QtCore, QtWidgets

from astock.data_jobs import DataJobs, publish_import
from astock.domain import CN, RulePeriod, dec
from astock.rule_history import read_rule_metadata
from astock.rules import STATUSES, rules_summary, validate_rule
from astock.ui_components import button, label


class RuleHistoryDialog(QtWidgets.QDialog):
    def __init__(self, root, identity, parent=None):
        super().__init__(parent)
        self.root, self.identity = root, identity
        self.meta, self.digest = read_rule_metadata(root / "datasets", identity)
        self.saved_id, self.token = "", None
        self.evidence = deepcopy(self.meta.get("rule_evidence", {}))
        self.preview = None
        self.jobs = DataJobs(root, self)
        self.jobs.message.connect(self.on_message)
        self.setWindowTitle("证券规则 · 按日期保存资料")
        self.resize(980, 590)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(label("为历史行情补充证券状态", "title"))
        intro = label("起止日均包含。添加区间后，须覆盖该证券全部行情日期；资料来源请填写公告链接或文件说明。"
                      "保存会生成独立版本，原数据及已完成的回测保持原样。")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.summary = label("原版本 · " + rules_summary(self.meta["rules"]))
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.grid = help_target(QtWidgets.QTableWidget(0, 7), 'rule_history_ui.RuleHistoryDialog.__init__.grid')
        self.grid.setHorizontalHeaderLabels(["证券", "起始日期", "结束日期", "状态", "涨跌幅", "可卖规则", "资料来源"])
        self.grid.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.grid.horizontalHeader().setStretchLastSection(True)
        for index, width in enumerate((105, 118, 118, 160, 95, 115, 230)):
            self.grid.setColumnWidth(index, width)
        layout.addWidget(self.grid, 1)
        row = QtWidgets.QHBoxLayout()
        self.symbols = help_target(QtWidgets.QComboBox(), 'rule_history_ui.RuleHistoryDialog.__init__.symbols')
        self.symbols.addItems(self.meta["symbols"])
        row.addWidget(self.symbols)
        self.add_button = help_target(button("新增日期区间", self.add_period), 'rule_history_ui.RuleHistoryDialog.__init__.add_button')
        self.remove_button = help_target(button("移除所选区间", self.remove_period), 'rule_history_ui.RuleHistoryDialog.__init__.remove_button')
        row.addWidget(self.add_button)
        row.addWidget(self.remove_button)
        row.addStretch()
        layout.addLayout(row)
        source_row = QtWidgets.QHBoxLayout()
        self.fetch_button = help_target(button("获取所选股票历史状态", self.fetch), 'rule_history_ui.RuleHistoryDialog.__init__.fetch_button')
        self.fetch_button.setObjectName("fetchStockStatus")
        source_row.addWidget(self.fetch_button)
        self.etf_button = help_target(button("查看 ETF 当前资料", self.view_etf), 'rule_history_ui.RuleHistoryDialog.__init__.etf_button')
        self.etf_button.setEnabled(self.meta["rules"][self.symbols.currentText()].kind == "etf")
        self.symbols.currentTextChanged.connect(lambda s: self.etf_button.setEnabled(self.meta["rules"][s].kind == "etf"))
        source_row.addWidget(self.etf_button)
        scope = label("股票可获取逐日状态；ETF 当前名单仅供核对，历史区间须另有日期依据。")
        scope.setWordWrap(True)
        source_row.addWidget(scope, 1)
        layout.addLayout(source_row)
        self.note = label("涨跌幅选“按状态计算”：ST 按生效日期计算，其他状态沿用标准比例。ETF 的 T+0 须有资料支持。")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.progress = QtWidgets.QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        actions = QtWidgets.QHBoxLayout()
        self.save_button = help_target(button("检查并另存版本", self.save, True), 'rule_history_ui.RuleHistoryDialog.__init__.save_button')
        self.cancel_button = help_target(button("取消检查", self.cancel), 'rule_history_ui.RuleHistoryDialog.__init__.cancel_button')
        self.cancel_button.setEnabled(False)
        actions.addWidget(self.save_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch()
        actions.addWidget(help_target(button("关闭", self.reject), 'rule_history_ui.RuleHistoryDialog.__init__.button'))
        layout.addLayout(actions)
        for symbol, rule in self.meta["rules"].items():
            for period in rule.history:
                self.append_period(symbol, period)

    def view_etf(self):
        from astock.catalog_ui import CatalogDialog
        dialog = CatalogDialog(self.root, lambda _: "", self, reference_only=True)
        dialog.category.setCurrentIndex(2)
        dialog.search.setText(self.symbols.currentText())
        if dialog.proxy.rowCount():
            dialog.table.selectRow(0)
        dialog.exec()

    def append_period(self, symbol, period):
        row = self.grid.rowCount()
        self.grid.insertRow(row)
        item = QtWidgets.QTableWidgetItem(symbol)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.grid.setItem(row, 0, item)
        for column, value in ((1, period.start), (2, period.end)):
            edit = help_target(QtWidgets.QDateEdit(QtCore.QDate.fromString(value, "yyyy-MM-dd")), 'rule_history_ui.RuleHistoryDialog.append_period.edit')
            edit.setDisplayFormat("yyyy-MM-dd")
            edit.setCalendarPopup(True)
            self.grid.setCellWidget(row, column, edit)
        status = help_target(QtWidgets.QComboBox(), 'rule_history_ui.RuleHistoryDialog.append_period.status')
        for code, text in STATUSES.items():
            status.addItem(text, code)
        status.setCurrentIndex(status.findData(period.status))
        self.grid.setCellWidget(row, 3, status)
        limit = help_target(QtWidgets.QComboBox(), 'rule_history_ui.RuleHistoryDialog.append_period.limit')
        for text, value in (("按状态计算", None), ("5%", "0.05"), ("10%", "0.10"), ("20%", "0.20")):
            limit.addItem(text, value)
        if period.limit_rate is not None:
            index = next((i for i in range(1, limit.count()) if dec(limit.itemData(i)) == period.limit_rate), -1)
            if index < 0:
                limit.addItem(f"{period.limit_rate * 100}%", str(period.limit_rate))
                index = limit.count() - 1
            limit.setCurrentIndex(index)
        self.grid.setCellWidget(row, 4, limit)
        settlement = help_target(QtWidgets.QComboBox(), 'rule_history_ui.RuleHistoryDialog.append_period.settlement')
        for text, value in (("沿用基础规则", None), ("T+1", 1), ("T+0", 0)):
            settlement.addItem(text, value)
        settlement.setCurrentIndex(settlement.findData(period.t_plus))
        self.grid.setCellWidget(row, 5, settlement)
        self.grid.setItem(row, 6, QtWidgets.QTableWidgetItem(period.source))
        self.grid.setCurrentCell(row, 6)

    def add_period(self):
        self.append_period(self.symbols.currentText(), RulePeriod(self.meta["start"][:10], self.meta["end"][:10], ""))

    def remove_period(self):
        for row in sorted({i.row() for i in self.grid.selectedIndexes()}, reverse=True):
            self.grid.removeRow(row)

    def collect(self):
        rules = deepcopy(self.meta["rules"])
        for rule in rules.values():
            rule.history = []
        for row in range(self.grid.rowCount()):
            limit = self.grid.cellWidget(row, 4).currentData()
            period = RulePeriod(self.grid.cellWidget(row, 1).date().toString("yyyy-MM-dd"),
                                self.grid.cellWidget(row, 2).date().toString("yyyy-MM-dd"),
                                self.grid.item(row, 6).text().strip(), self.grid.cellWidget(row, 3).currentData(),
                                dec(limit) if limit is not None else None, self.grid.cellWidget(row, 5).currentData())
            rules[self.grid.item(row, 0).text()].history.append(period)
        for rule in rules.values():
            rule.history.sort(key=lambda p: p.start)
            validate_rule(rule)
        return rules

    def busy(self, value):
        for widget in (self.grid, self.symbols, self.add_button, self.remove_button, self.save_button, self.fetch_button):
            widget.setEnabled(not value)
        self.cancel_button.setEnabled(value)
        self.progress.setVisible(value)
        self.progress.setRange(0, 0)

    def save(self):
        try:
            rules = self.collect()
            if rules == self.meta["rules"]:
                self.note.setText("规则尚未修改；无需另存相同版本。")
                return
            self.token = self.jobs.start("rules", root=str(self.root / "datasets"), identity=self.identity,
                                         source=str(self.root / "datasets" / f"{self.identity}.json"),
                                         metadata_sha256=self.digest, rules=rules, rule_evidence=self.evidence)
            self.busy(True)
            self.note.setText("正在后台检查日期覆盖；可取消。")
        except Exception as error:
            self.note.setText(str(error))

    def cancel(self):
        self.jobs.cancel("rules")
        self.jobs.cancel("rule_fetch")
        self.token = None
        self.busy(False)
        self.note.setText("检查已取消，原数据保持原样。")

    def fetch(self):
        rule = self.meta["rules"][self.symbols.currentText()]
        if rule.kind != "stock":
            self.note.setText("ETF 的 T+0/T+1 不能从股票状态接口推断；请添加有来源的日期区间。")
            return
        if self.meta.get("demo"):
            self.note.setText("教学数据为合成行情，不附加真实证券状态。请先在数据中心选择实际历史行情。")
            return
        self.token = self.jobs.start("rule_fetch", rule=rule,
                                     start=datetime.fromisoformat(self.meta["start"]).astimezone(CN).date().isoformat(),
                                     end=datetime.fromisoformat(self.meta["end"]).astimezone(CN).date().isoformat())
        self.busy(True)
        self.note.setText("正在后台获取日期资料，可随时取消；当前填写内容保持原样。")

    def show_status_preview(self, result):
        from astock.historical_status import NOTICE
        audit, symbol = result["audit"], result["symbol"]
        preview = QtWidgets.QDialog(self)
        self.preview = preview
        preview.setObjectName("stockStatusPreview")
        preview.setWindowTitle("历史状态资料预览 · " + symbol)
        preview.resize(800, 490)
        layout = QtWidgets.QVBoxLayout(preview)
        title = label(f"{symbol} · {audit['request']['start']} 至 {audit['request']['end']}", "title")
        layout.addWidget(title)
        text = label(f"来源：BaoStock · 收到 {len(audit['rows'])} 个交易日记录 · "
                     f"上市日期 {audit['basic'][0]['ipoDate']}\n" + NOTICE)
        text.setWordWrap(True)
        layout.addWidget(text)
        grid = help_target(QtWidgets.QTableWidget(len(result["periods"]), 3), 'rule_history_ui.RuleHistoryDialog.show_status_preview.grid')
        grid.setObjectName("stockStatusPeriods")
        grid.setHorizontalHeaderLabels(["开始日期", "结束日期", "历史状态"])
        grid.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        grid.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        for row, period in enumerate(result["periods"]):
            for column, value in enumerate((period.start, period.end, STATUSES[period.status])):
                grid.setItem(row, column, QtWidgets.QTableWidgetItem(value))
        layout.addWidget(grid, 1)
        missing = audit["missing_dates"]
        note = label((f"缺少 {len(missing)} 个交易日资料：" + "、".join(missing[:6]) + "。填入后须补齐才能回测。")
                     if missing else "已覆盖请求范围的交易日。原始资料及来源将随新版本保存。")
        note.setWordWrap(True)
        layout.addWidget(note)
        actions = QtWidgets.QHBoxLayout()
        existing = any(self.grid.item(i, 0).text() == symbol for i in range(self.grid.rowCount()))
        def apply():
            for row in reversed(range(self.grid.rowCount())):
                if self.grid.item(row, 0).text() == symbol:
                    self.grid.removeRow(row)
            for period in result["periods"]:
                self.append_period(symbol, period)
            self.evidence[symbol] = deepcopy(audit)
            self.note.setText(f"已填入 {symbol} 的 {len(result['periods'])} 个区间；请核对后点击「检查并另存版本」。")
            preview.accept()
        adopt = help_target(button("替换所选证券的待保存区间" if existing else "填入待保存区间", apply, True), 'rule_history_ui.RuleHistoryDialog.show_status_preview.adopt')
        adopt.setObjectName("applyStockStatus")
        actions.addWidget(adopt)
        actions.addWidget(help_target(button("返回，不采用", preview.reject), 'rule_history_ui.RuleHistoryDialog.show_status_preview.button'))
        layout.addLayout(actions)
        preview.open()

    def on_message(self, message):
        if message.get("token") != self.token:
            return
        if message["type"] == "progress":
            self.note.setText(message["phase"])
            return
        self.token = None
        self.busy(False)
        if message["type"] == "error":
            self.note.setText(message["message"])
            return
        if message["kind"] == "rule_fetch":
            self.show_status_preview(message["result"])
            return
        try:
            publish_import(self.root / "datasets", message["request"], message["result"])
            self.saved_id = message["result"]["meta"]["id"]
            self.accept()
        except Exception as error:
            self.note.setText(str(error))

    def done(self, result):
        self.jobs.close()
        super().done(result)
