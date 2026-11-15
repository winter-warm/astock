from astock.help_registry import help_target
from html import escape
import unicodedata

from PySide6 import QtCore, QtWidgets

from astock.catalog import BOARD_NAMES, SEGMENTS, catalog_records, load_catalog, publish_catalog
from astock.data_jobs import DataJobs
from astock.etf_reference import NOTICE
from astock.rules import default_rule
from astock.ui_components import button, label


def search_text(value):
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


class CatalogModel(QtCore.QAbstractTableModel):
    HEADERS = ("证券代码", "名称", "类别", "板块", "上市日期")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.records = []

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        row = self.records[index.row()]
        return (row["symbol"], row["name"], "ETF" if row["kind"] == "etf" else "股票",
                BOARD_NAMES[row["board"]], row["listing_date"] or "未提供")[index.column()]

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if role == QtCore.Qt.ItemDataRole.DisplayRole and orientation == QtCore.Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def replace(self, records):
        self.beginResetModel()
        self.records = records
        self.endResetModel()


class CatalogFilter(QtCore.QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.query, self.kind = "", ""

    def filterAcceptsRow(self, row, parent):
        record = self.sourceModel().records[row]
        haystack = search_text(record["symbol"] + " " + record["symbol"][-2:] + record["symbol"][:6]
                               + " " + record["name"])
        return (not self.kind or record["kind"] == self.kind) and all(search_text(x) in haystack for x in self.query.split())

    def update_filter(self, query, kind):
        self.beginFilterChange()
        self.query, self.kind = query.strip().casefold(), kind
        self.endFilterChange(QtCore.QSortFilterProxyModel.Direction.Rows)


class CatalogDialog(QtWidgets.QDialog):
    def __init__(self, root, add_selected, parent=None, *, reference_only=False):
        super().__init__(parent)
        self.root, self.add_selected = root, add_selected
        self.setWindowTitle("证券目录 · 按代码或名称查找")
        self.resize(880, 620)
        self.setMinimumSize(600, 440)
        self.token = None
        self.current, warning = load_catalog(root)
        self.jobs = DataJobs(root, self)
        self.jobs.message.connect(self.receive)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(label("搜索股票与场内 ETF", "title"))
        filters = QtWidgets.QHBoxLayout()
        self.search = help_target(QtWidgets.QLineEdit(), 'catalog_ui.CatalogDialog.__init__.search')
        self.search.setPlaceholderText("输入代码或名称，如 600000、浦发、沪深300")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("证券代码或名称")
        self.category = help_target(QtWidgets.QComboBox(), 'catalog_ui.CatalogDialog.__init__.category')
        for text, value in (("全部", ""), ("股票", "stock"), ("ETF", "etf")):
            self.category.addItem(text, value)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.category)
        self.refresh_button = help_target(button("更新目录", self.refresh), 'catalog_ui.CatalogDialog.__init__.refresh_button')
        self.cancel_button = help_target(button("取消更新", self.cancel), 'catalog_ui.CatalogDialog.__init__.cancel_button')
        self.cancel_button.setEnabled(False)
        filters.addWidget(self.refresh_button)
        filters.addWidget(self.cancel_button)
        layout.addLayout(filters)
        self.sources = label("", "muted", True)
        layout.addWidget(self.sources)
        self.table = help_target(QtWidgets.QTableView(), 'catalog_ui.CatalogDialog.__init__.table')
        self.model = CatalogModel(self)
        self.proxy = CatalogFilter(self)
        self.proxy.setSourceModel(self.model)
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)
        self.count = label("", "muted")
        layout.addWidget(self.count)
        self.details = help_target(QtWidgets.QTextBrowser(), 'catalog_ui.CatalogDialog.__init__.details')
        self.details.setMaximumHeight(175)
        self.details.setOpenExternalLinks(True)
        layout.addWidget(self.details)
        self.status = label(warning or "本机已保存目录，可离线搜索。", "muted", True)
        self.status.setMaximumHeight(80)
        self.status.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        actions = QtWidgets.QHBoxLayout()
        actions.addWidget(label("Ctrl / Shift 可多选 · 最多同时关注 20 个", "muted"), 1)
        self.add_button = help_target(button("加入在线标的", self.add, True), 'catalog_ui.CatalogDialog.__init__.add_button')
        self.add_button.setEnabled(False)
        actions.addWidget(self.add_button)
        self.add_button.setVisible(not reference_only)
        actions.addWidget(help_target(button("关闭", self.close), 'catalog_ui.CatalogDialog.__init__.button'))
        layout.addLayout(actions)
        self.search.textChanged.connect(self.filter)
        self.category.currentIndexChanged.connect(self.filter)
        self.table.selectionModel().selectionChanged.connect(self.selection_changed)
        if not reference_only:
            self.table.doubleClicked.connect(self.add)
        self.populate()
        self.search.setFocus()
        # A blocked upstream cannot keep a data job alive indefinitely.
        self.deadline = QtCore.QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(self.timeout)

    def populate(self):
        self.model.replace(catalog_records(self.current))
        pieces = []
        for key, name in SEGMENTS.items():
            part = self.current["segments"].get(key)
            pieces.append(name + (f"：{len(part['records']):,} 项 / {part['refreshed_at'][:16].replace('T', ' ')}"
                                  + (f"（排除存托凭证或重复项 {part['excluded_count']} 条）" if part.get("excluded_count") else "")
                                  if part else "：未下载"))
        self.sources.setText("目录获取时间 · " + "；".join(pieces))
        self.filter()

    def filter(self, *_):
        self.proxy.update_filter(self.search.text(), self.category.currentData())
        self.count.setText(f"匹配 {self.proxy.rowCount():,} / {self.model.rowCount():,} 项"
                           + (" · 没有结果，可更换关键词或更新目录" if not self.proxy.rowCount() else ""))
        self.selection_changed()

    def selected(self):
        return [self.model.records[self.proxy.mapToSource(i).row()]
                for i in sorted(self.table.selectionModel().selectedRows(), key=lambda i: i.row())]

    def selection_changed(self, *_):
        entries = self.selected()
        self.add_button.setEnabled(bool(entries))
        if not entries:
            self.details.setPlainText("选择证券查看来源与默认模拟设置。ETF 资料含交易所当前的 T+0/T+1 与涨跌幅名单；历史规则仍需对应日期的依据。")
            return
        row = entries[0]
        rule = None
        try:
            rule = default_rule(row["symbol"], row["name"])
            rule_note = f"历史数据默认模拟设置：T+{rule.t_plus}，涨跌幅 {rule.limit_rate * 100:g}%，价格单位 {rule.tick}。"
            if row["kind"] == "etf" and rule.t_plus == 1:
                rule_note += " 未列入已维护的 T+0 名单时，按保守 T+1 处理。"
        except ValueError:
            rule_note = "当前撮合规则暂不支持此代码，不能加入在线标的。"
        reference = row.get("etf_reference")
        reference_note = ""
        if reference:
            limit = "20%" if reference["limit_rate"] == "0.20" else "10%"
            reference_note = (f"<b>交易所当前名单：T+{reference['t_plus']} · 涨跌幅 {limit}</b><br>"
                              f"{escape(NOTICE)}<br>"
                              f"<a style='color:#559cdd' href='{escape(reference['source'], quote=True)}'>查看交易所来源</a> · "
                              f"名单日期：{escape(reference['source_date'] or '来源未提供')} · "
                              f"获取：{escape(reference['observed_at'][:19].replace('T', ' '))}<br>")
            if rule and (rule.t_plus != reference["t_plus"] or str(rule.limit_rate) != reference["limit_rate"]):
                rule_note += " 与当前名单不同；历史回测可在数据中心「证券规则」按有效日期另存修订。"
        self.details.setHtml(f"<b>{escape(row['symbol'])} · {escape(row['name'])}</b><br>"
                             f"{reference_note}{escape(rule_note)}<br>"
                             f"来源：{escape(row['source'])}；获取时间：{escape(row['refreshed_at'] or '内置资料，无在线更新时间')}<br>"
                             "新建实时账户核对当日名单后采用当前属性；已有实时账户须暂停后更新当日规则。"
                             "历史回测仍以数据包保存的规则为准。")

    def add(self, *_):
        entries = self.selected()
        if not entries:
            return
        try:
            self.status.setText(self.add_selected(entries))
        except ValueError as error:
            self.status.setText(str(error))

    def refresh(self):
        try:
            self.token = self.jobs.start("catalog")
            self.refresh_button.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.deadline.start(90000)
            self.status.setText("正在更新目录；仍可搜索已有资料。关闭窗口会取消更新。")
        except Exception as error:
            self.status.setText("无法开始更新：" + str(error))

    def cancel(self):
        self.jobs.cancel("catalog")
        self.token = None
        self.deadline.stop()
        self.refresh_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status.setText("更新已取消，已有目录保持不变。")

    def timeout(self):
        self.cancel()
        self.status.setText("目录获取超过 90 秒，已停止；已有目录保留，可稍后再试。")

    def receive(self, message):
        if self.token is None or message["token"] != self.token:
            return
        if message["type"] == "progress":
            self.status.setText(message["phase"] + "… 已有目录仍可搜索。")
            return
        self.token = None
        self.deadline.stop()
        self.refresh_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if message["type"] == "error":
            self.status.setText("目录更新失败，已有资料保留：" + message["message"])
            return
        try:
            self.current = publish_catalog(self.root, self.current, message["result"])
            self.populate()
            failures = [SEGMENTS[key] + "：" + value["error"]
                        for key, value in message["result"]["attempts"].items() if value["error"]]
            count = len(message["result"]["segments"])
            self.status.setToolTip("；".join(failures))
            self.status.setText(f"已更新 {count} 个分区。" + ("失败分区保留旧资料：" + "；".join(x[:90] for x in failures)
                                                         if failures else "目录已保存，可离线搜索。"))
        except (ValueError, KeyError, TypeError, OSError) as error:
            self.status.setText("目录保存失败，已有资料保留：" + str(error))

    def done(self, result):
        self.cancel()
        self.jobs.close()
        super().done(result)

    def closeEvent(self, event):
        self.cancel()
        self.jobs.close()
        super().closeEvent(event)
