"""Explicit date and benchmark configuration for a new historical run."""
from astock.help_registry import help_target
from PySide6 import QtCore, QtWidgets

from astock.ui_components import INITIAL_CAPITAL_RANGE, label
from astock.data_identity import display_name, source_summary


class BacktestSetup(QtWidgets.QDialog):
    def __init__(self, meta, options, initial, parent=None, *, datasets=None, saved_options=None):
        super().__init__(parent)
        self.setWindowTitle("回测设置")
        self.resize(680, 620)
        self.datasets = list(datasets) if datasets is not None else ([meta] if meta else [])
        self.saved_options = dict(saved_options or {})
        if meta:
            self.saved_options[meta.get('id', '')] = dict(options)
        self.current_meta = None
        self.range_start = self.range_end = QtCore.QDate()
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(label('选择本次运行使用的数据；保存后应用，取消不改变当前选择。', wrap=True))
        self.dataset = help_target(QtWidgets.QComboBox(), 'backtest_setup.BacktestSetup.__init__.dataset')
        for item in self.datasets:
            kind = '快照回放' if item.get('kind') == 'quote' else 'K 线回测'
            self.dataset.addItem(f"{display_name(item)} · {kind}", item.get('id', ''))
            self.dataset.setItemData(self.dataset.count() - 1, source_summary(item), QtCore.Qt.ItemDataRole.ToolTipRole)
        if meta:
            self.dataset.setCurrentIndex(max(0, self.dataset.findData(meta.get('id', ''))))
        layout.addWidget(self.dataset)
        self.selection_note = label('', wrap=True)
        layout.addWidget(self.selection_note)
        self.coverage = label('', 'muted', True)
        layout.addWidget(self.coverage)
        presets = QtWidgets.QHBoxLayout()
        self.range_buttons = {}
        for key, title in (("full", "全部区间"), ("first", "前半段 · 探索"), ("last", "后半段 · 检验")):
            control = help_target(QtWidgets.QPushButton(title), 'backtest_setup.BacktestSetup.__init__.control')
            control.clicked.connect(lambda checked=False, selected=key: self.select_range(selected))
            self.range_buttons[key] = control
            presets.addWidget(control)
        layout.addLayout(presets)
        form = QtWidgets.QFormLayout()
        self.dates = []
        for key, title in (("start", "开始日期"), ("end", "结束日期")):
            field = help_target(QtWidgets.QDateEdit(), 'backtest_setup.BacktestSetup.__init__.field')
            field.setCalendarPopup(True)
            field.setDisplayFormat("yyyy-MM-dd")
            form.addRow(title, field)
            self.dates.append(field)
        self.benchmark = help_target(QtWidgets.QComboBox(), 'backtest_setup.BacktestSetup.__init__.benchmark')
        form.addRow("收益对比基准", self.benchmark)
        self.capital = help_target(QtWidgets.QDoubleSpinBox(), 'backtest_setup.BacktestSetup.__init__.capital')
        self.capital.setRange(*INITIAL_CAPITAL_RANGE)
        self.capital.setValue(initial)
        form.addRow("初始资金（元）", self.capital)
        self.period = label('')
        form.addRow("运行周期", self.period)
        layout.addLayout(form)
        self.split_note = label(
            "前后半段按日历日期划分，不按行情条数。可先在前半段探索，固定参数后再单独运行后半段。"
            "每次运行都从空仓开始，不继承上一段持仓或指标；反复查看后半段并调参会使其失去独立检验作用。"
            "区间快捷选择不等于自动样本外验证。", "muted", True)
        layout.addWidget(self.split_note)
        layout.addWidget(label("更换证券或周期请先选择对应数据集。所选日期内从空仓开始，指标仅使用区间内行情，前几期可能没有交易。\n费用与滑点沿用右侧撮合设置；基准是所选证券的价格买入持有。", "muted", True))
        self.error = label("", "muted", True)
        layout.addWidget(self.error)
        self.actions = help_target(QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save |
                                            QtWidgets.QDialogButtonBox.StandardButton.Cancel), 'backtest_setup.BacktestSetup.__init__.actions')
        self.actions.accepted.connect(self.save)
        self.actions.rejected.connect(self.reject)
        layout.addWidget(self.actions)
        self.dataset.currentIndexChanged.connect(self.update_dataset)
        self.update_dataset()

    def selected_meta(self):
        index = self.dataset.currentIndex()
        return self.datasets[index] if 0 <= index < len(self.datasets) else None

    def update_dataset(self, *_):
        if self.current_meta and self.current_meta.get('kind', 'bar') == 'bar':
            self.saved_options[self.current_meta.get('id', '')] = self.options()
        self.current_meta = meta = self.selected_meta()
        is_bar = bool(meta) and meta.get('kind', 'bar') == 'bar'
        for field in (*self.dates, self.benchmark):
            field.setEnabled(is_bar)
        self.capital.setEnabled(bool(meta))
        self.actions.button(QtWidgets.QDialogButtonBox.StandardButton.Save).setEnabled(bool(meta))
        self.split_note.setVisible(is_bar)
        self.error.clear()
        if not meta:
            self.selection_note.setText('暂无可用数据。请先到数据中心导入或下载数据，再设置回测。')
            self.coverage.clear()
            self.period.clear()
            for control in self.range_buttons.values():
                control.setEnabled(False)
            return
        self.range_start = QtCore.QDate.fromString(str(meta['start'])[:10], 'yyyy-MM-dd')
        self.range_end = QtCore.QDate.fromString(str(meta['end'])[:10], 'yyyy-MM-dd')
        options = self.saved_options.get(meta.get('id', ''), {})
        for key, field in zip(('start', 'end'), self.dates):
            field.setDateRange(self.range_start, self.range_end)
            field.setDate(QtCore.QDate.fromString(options.get(key, str(meta[key])[:10]), 'yyyy-MM-dd'))
        self.benchmark.clear()
        self.benchmark.addItems(meta['symbols'])
        self.benchmark.setCurrentText(options.get('benchmark', meta['symbols'][0] if meta['symbols'] else ''))
        self.period.setText(meta['period'] + '（由所选数据决定）')
        self.selection_note.setText(
            'K 线回测：可以设置日期区间和收益基准。' if is_bar else
            '当前是快照回放，使用完整录制区间；可调整初始资金。要按日期回测，请在上方选择 K 线数据。')
        self.coverage.setText(
            source_summary(meta) + '\n' +
            f"证券：{', '.join(meta['symbols'])}\n"
            '覆盖起止时间不代表中间无缺口；请在数据中心检查缺口及权益资料。')
        can_split = is_bar and self.range_start.daysTo(self.range_end) >= 1
        self.range_buttons['full'].setEnabled(is_bar)
        for key in ('first', 'last'):
            self.range_buttons[key].setEnabled(can_split)
            self.range_buttons[key].setToolTip(
                '按数据覆盖的日历日期均分；两段不重叠，不保证两段均有行情。' if can_split else
                '快照使用完整录制区间。' if not is_bar else '数据仅覆盖一天，无法拆成两个不重叠的日期区间。')

    def options(self):
        return {"start": self.dates[0].date().toString("yyyy-MM-dd"),
                "end": self.dates[1].date().toString("yyyy-MM-dd"), "benchmark": self.benchmark.currentText()}

    def select_range(self, selected):
        start, end = self.range_start, self.range_end
        days = start.daysTo(end) + 1
        if selected != "full" and days < 2:
            return
        if selected == "first":
            end = start.addDays((days + 1) // 2 - 1)
        elif selected == "last":
            start = start.addDays((days + 1) // 2)
        self.dates[0].setDate(start)
        self.dates[1].setDate(end)
        self.error.clear()

    def save(self):
        if not self.current_meta:
            return
        if self.current_meta.get('kind', 'bar') == 'bar' and self.dates[0].date() > self.dates[1].date():
            self.error.setText("开始日期不能晚于结束日期。")
            return
        self.accept()
