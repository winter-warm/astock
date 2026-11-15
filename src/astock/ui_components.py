from __future__ import annotations

import re
from datetime import datetime
import math

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg


INITIAL_CAPITAL_RANGE = (1000, 100000000)


DARK = {
    "bg": "#0b0f16", "surface": "#111722", "raised": "#1b2432", "line": "#2a3546",
    "text": "#e1e6ee", "muted": "#9aa8bc", "accent": "#3b82d0", "up": "#f07983", "down": "#53c6aa",
}
LIGHT = {
    "bg": "#e9edf2", "surface": "#ffffff", "raised": "#e0e7ef", "line": "#bbc6d4",
    "text": "#202d41", "muted": "#53647b", "accent": "#2468b1", "up": "#d34658", "down": "#168568",
}


def stylesheet(theme):
    c = DARK if theme == "dark" else LIGHT
    return f"""
    QWidget {{ color: {c['text']}; font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 12px; }}
    QMainWindow, QWidget#workspace {{ background: {c['bg']}; }}
    QDialog {{ background: {c['surface']}; }}
    QWidget#sidepanel {{ background: {c['surface']}; }}
    QToolBar {{ background: {c['surface']}; border: 0; spacing: 3px; padding: 2px; }}
    QToolButton {{ background: {c['raised']}; border: 1px solid {c['line']}; border-radius: 1px; padding: 3px 5px; }}
    QToolButton:hover {{ border-color: {c['accent']}; }}
    QDockWidget {{ font-weight: 600; }}
    QDockWidget::title {{ color: {c['text']}; background: {c['surface']}; padding: 4px 6px; border-bottom: 1px solid {c['line']}; }}
    QFrame#panel, QFrame#metric {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 1px; }}
    QFrame#topbar {{ background: {c['surface']}; border-bottom: 1px solid {c['line']}; }}
    QLabel#brand {{ font-size: 15px; font-weight: 700; color: {c['text']}; letter-spacing: 1px; }}
    QLabel#title {{ font-size: 15px; font-weight: 600; }}
    QLabel#subtitle, QLabel#muted {{ color: {c['muted']}; }}
    QLabel#badge {{ color: {c['text']}; background: {c['raised']}; border-radius: 1px; padding: 3px 6px; }}
    QLabel#metricValue {{ font-family: 'Consolas'; font-size: 14px; font-weight: 600; }}
    QPushButton {{ background: {c['raised']}; border: 1px solid {c['line']}; border-radius: 1px; padding: 4px 8px; }}
    QPushButton:hover {{ border-color: {c['accent']}; }}
    QPushButton:disabled {{ color: {c['muted']}; background: {c['surface']}; }}
    QPushButton#primary {{ background: {c['accent']}; color: #ffffff; font-weight: 600; border: 1px solid {c['accent']}; }}
    QPushButton#danger {{ color: {c['up']}; }}
    QPushButton#nav {{ border: 0; border-bottom: 2px solid transparent; background: transparent; padding: 5px 10px; color: {c['muted']}; font-weight: 600; }}
    QPushButton#nav:checked {{ background: {c['raised']}; color: {c['text']}; border-bottom-color: {c['accent']}; }}
    QPushButton#lessonNav:checked {{ border-color: {c['accent']}; color: {c['accent']}; }}
    QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {{
        background: {c['bg']}; border: 1px solid {c['line']}; border-radius: 1px; padding: 3px 5px; selection-background-color: #244e7b; }}
    QComboBox::drop-down {{ border: 0; width: 20px; }}
    QComboBox QAbstractItemView {{ background: {c['raised']}; selection-background-color: #244e7b; selection-color: #ffffff; }}
    QTableView, QTreeWidget {{ background: {c['surface']}; alternate-background-color: {c['bg']}; border: 0; gridline-color: {c['line']}; }}
    QTreeWidget::item {{ padding: 3px 3px; }}
    QTableView::item {{ padding: 1px 4px; }}
    QTreeWidget::item:selected, QTableView::item:selected {{ background: #244e7b; color: #ffffff; }}
    QHeaderView::section {{ background: {c['raised']}; color: {c['text']}; border: 0; border-right: 1px solid {c['line']}; border-bottom: 1px solid {c['line']}; padding: 4px 6px; font-weight: 400; }}
    QTabWidget, QTabBar {{ background: {c['surface']}; }}
    QTabWidget::pane {{ border: 1px solid {c['line']}; background: {c['surface']}; }}
    QTabBar::tab {{ background: {c['surface']}; color: {c['muted']}; padding: 5px 10px; border-right: 1px solid {c['line']}; border-bottom: 2px solid transparent; }}
    QTabBar::tab:selected {{ background: {c['raised']}; color: {c['text']}; border-bottom: 2px solid {c['accent']}; }}
    QGroupBox {{ border: 1px solid {c['line']}; border-radius: 1px; margin-top: 11px; padding-top: 9px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 7px; color: {c['muted']}; }}
    QScrollArea {{ border: 0; background: {c['surface']}; }}
    QScrollBar:vertical {{ background: {c['bg']}; width: 8px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {c['line']}; border-radius: 1px; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: {c['bg']}; height: 8px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {c['line']}; border-radius: 1px; min-width: 24px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: {c['bg']}; }}
    QMenuBar, QMenu, QStatusBar {{ background: {c['surface']}; }}
    QMenu::item:selected {{ background: {c['raised']}; }}
    QMenu::item {{ padding: 4px 22px; }}
    QMenuBar::item {{ padding: 3px 7px; }}
    QStatusBar {{ border-top: 1px solid {c['line']}; }}
    QProgressBar {{ background: {c['bg']}; border: 1px solid {c['line']}; border-radius: 1px; text-align: center; }}
    QProgressBar::chunk {{ background: {c['accent']}; }}
    QSplitter::handle {{ background: {c['line']}; }}
    QToolTip {{ background: {c['raised']}; color: {c['text']}; border: 1px solid {c['line']}; padding: 5px; }}
    """


def label(text, name=None, wrap=False):
    widget = QtWidgets.QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback=None, primary=False):
    widget = QtWidgets.QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    if callback:
        widget.clicked.connect(callback)
    return widget


class WorkspaceStack(QtWidgets.QStackedWidget):
    """Inactive editors must not dictate the height of the visible analysis page."""
    def __init__(self):
        super().__init__()
        self.layout().setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetNoConstraint)
        self.currentChanged.connect(lambda _: self.updateGeometry())

    def minimumSizeHint(self):
        page = self.currentWidget()
        return page.minimumSizeHint() if page else QtCore.QSize(0, 0)

    def sizeHint(self):
        page = self.currentWidget()
        return page.sizeHint() if page else QtCore.QSize(0, 0)

    def hasHeightForWidth(self):
        page = self.currentWidget()
        return bool(page and page.hasHeightForWidth())

    def heightForWidth(self, width):
        # Qt's aggregate heightForWidth includes the charts' preferred height
        # (roughly 500 px), even though they have a smaller usable minimum.
        # The scroll area needs the minimum; the page layout distributes room.
        return self.minimumSizeHint().height()


def table(headers):
    widget = QtWidgets.QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setAlternatingRowColors(True)
    widget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.verticalHeader().hide()
    widget.verticalHeader().setDefaultSectionSize(24)
    widget.setShowGrid(False)
    widget.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    return widget


def populate(widget, rows, identifiers=None):
    widget.setUpdatesEnabled(False)
    current = widget.currentRow()
    widget.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QtWidgets.QTableWidgetItem(str(value))
            if identifiers and c == 0:
                item.setData(QtCore.Qt.ItemDataRole.UserRole, identifiers[r])
            if c and re.fullmatch(r"[-+\d.,% ]+", str(value)):
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            widget.setItem(r, c, item)
    if current >= 0 and current < len(rows):
        widget.selectRow(current)
    widget.setUpdatesEnabled(True)


class RecordModel(QtCore.QAbstractTableModel):
    """Keep every record, format only visible rows instead of allocating cells."""
    def __init__(self, headers, format_row, parent=None):
        super().__init__(parent)
        self.headers, self.format_row = headers, format_row
        self.records = []
        self.cache = {}

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if orientation == QtCore.Qt.Orientation.Horizontal and role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self.headers[section]

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.records):
            return None
        if role not in (QtCore.Qt.ItemDataRole.DisplayRole, QtCore.Qt.ItemDataRole.ToolTipRole):
            return None
        row = index.row()
        if row not in self.cache:
            if len(self.cache) >= 1024:
                self.cache.clear()
            self.cache[row] = tuple(str(v) for v in self.format_row(self.records[row]))
        return self.cache[row][index.column()]

    def replace(self, records):
        self.beginResetModel()
        self.records = records
        self.cache.clear()
        self.endResetModel()


class RecordTable(QtWidgets.QTableView):
    itemSelectionChanged = QtCore.Signal()

    def __init__(self, headers, format_row, widths):
        super().__init__()
        self.record_model = RecordModel(headers, format_row, self)
        self.setModel(self.record_model)
        self.run_id = None
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(24)
        self.setShowGrid(False)
        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        for index, width in enumerate(widths):
            self.setColumnWidth(index, width)
        self.selectionModel().selectionChanged.connect(lambda *_: self.itemSelectionChanged.emit())

    def currentRow(self):
        return self.currentIndex().row()

    def current_record(self):
        row = self.currentRow()
        return self.record_model.records[row] if 0 <= row < len(self.record_model.records) else None

    def set_records(self, records, run_id):
        row = self.currentRow() if self.run_id == run_id else -1
        scroll = self.verticalScrollBar().value() if self.run_id == run_id else 0
        self.run_id = run_id
        blocked = self.blockSignals(True)
        self.record_model.replace(records)
        if 0 <= row < len(records):
            self.selectRow(row)
        self.verticalScrollBar().setValue(scroll)
        self.blockSignals(blocked)


class PythonHighlighter(QtGui.QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []
        for pattern, color in [
            (r"\b(?:class|def|if|elif|else|for|while|return|import|from|as|and|or|not|in|is|None|True|False|raise|try|except|with|pass)\b", "#c694ee"),
            (r"\b(?:self|ctx|Strategy|UserStrategy)\b", "#7dc7ed"),
            (r"\b\d+(?:\.\d+)?\b", "#e9b66b"),
            (r"(?:\"[^\"\n]*\"|'[^'\n]*')", "#a6d79c"),
            (r"#[^\n]*", "#71849f"),
        ]:
            fmt = QtGui.QTextCharFormat()
            fmt.setForeground(QtGui.QColor(color))
            self.rules.append((re.compile(pattern), fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)

    def theme(self, name):
        colors = ["#c694ee", "#7dc7ed", "#e9b66b", "#a6d79c", "#71849f"] if name == "dark" else [
            "#7545a5", "#176a9b", "#995600", "#257441", "#65758a"]
        for (_, fmt), color in zip(self.rules, colors):
            fmt.setForeground(QtGui.QColor(color))
        self.rehighlight()


class LineNumbers(QtWidgets.QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QtCore.QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_gutter(event)


class CodeEditor(QtWidgets.QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.theme_name = "dark"
        self.setFont(QtGui.QFont("Consolas", 11))
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.gutter = LineNumbers(self)
        self.highlighter = PythonHighlighter(self.document())
        self.blockCountChanged.connect(lambda _: self.setViewportMargins(self.gutter_width(), 0, 0, 0))
        self.updateRequest.connect(self.update_gutter)
        self.cursorPositionChanged.connect(self.highlight_line)
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def gutter_width(self):
        return 15 + self.fontMetrics().horizontalAdvance("9") * max(3, len(str(self.blockCount())))

    def update_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        r = self.contentsRect()
        self.gutter.setGeometry(r.left(), r.top(), self.gutter_width(), r.height())

    def paint_gutter(self, event):
        painter = QtGui.QPainter(self.gutter)
        painter.fillRect(event.rect(), QtGui.QColor("#151e2b" if self.theme_name == "dark" else "#e3eaf3"))
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = int(self.blockBoundingRect(block).height())
            if block.isVisible() and top + height >= event.rect().top():
                painter.setPen(QtGui.QColor("#71849f"))
                painter.drawText(0, top, self.gutter.width() - 7, self.fontMetrics().height(),
                                 QtCore.Qt.AlignmentFlag.AlignRight, str(number + 1))
            block = block.next()
            top += height
            number += 1

    def highlight_line(self):
        selection = QtWidgets.QTextEdit.ExtraSelection()
        selection.format.setBackground(QtGui.QColor("#25364a" if self.theme_name == "dark" else "#d5e3f1"))
        selection.format.setProperty(QtGui.QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])

    def theme(self, name):
        self.theme_name = name
        self.highlighter.theme(name)
        self.highlight_line()
        self.gutter.update()

    def goto_line(self, line):
        block = self.document().findBlockByNumber(max(0, line - 1))
        if block.isValid():
            self.setTextCursor(QtGui.QTextCursor(block))
            self.centerCursor()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_Tab:
            self.insertPlainText("    ")
        else:
            super().keyPressEvent(event)


class CandleItem(pg.GraphicsObject):
    def __init__(self):
        super().__init__()
        self.picture = QtGui.QPicture()
        self.bounds = QtCore.QRectF()

    def set_data(self, points):
        self.prepareGeometryChange()
        self.picture = QtGui.QPicture()
        painter = QtGui.QPainter(self.picture)
        for i, p in enumerate(points):
            color = QtGui.QColor("#f07983" if p["close"] >= p["open"] else "#53c6aa")
            painter.setPen(QtGui.QPen(color, 0))
            painter.drawLine(QtCore.QPointF(i, p["low"]), QtCore.QPointF(i, p["high"]))
            painter.setBrush(color)
            low, high = sorted((p["open"], p["close"]))
            height = max(high - low, max(high, .01) * .00015)
            painter.drawRect(QtCore.QRectF(i - .3, low, .6, height))
        painter.end()
        # QPicture.boundingRect uses integer coordinates: a 4.21--4.23 ETF
        # would wrongly occupy whole-yuan bounds and appear almost flat.
        if points:
            low = min(p["low"] for p in points)
            high = max(max(p["high"], min(p["open"], p["close"]) +
                           max(abs(p["close"] - p["open"]), max(p["open"], p["close"], .01) * .00015))
                       for p in points)
            self.bounds = QtCore.QRectF(-.3, low, len(points) - .4, max(high - low, .000001))
        else:
            self.bounds = QtCore.QRectF()
        self.update()

    def paint(self, painter, *args):
        painter.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return self.bounds


class ObservationAxis(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.times = []
        self.setStyle(tickFont=QtGui.QFont("Segoe UI", 8))

    def tickValues(self, minVal, maxVal, size):
        # Date labels need room even in the narrow research preview. A single
        # readable level avoids drawing dense minor labels over major labels.
        low, high = max(0, minVal), min(len(self.times) - 1, maxVal)
        if high < low:
            return []
        raw = max(1, (high - low) / max(1, int(size / 110)))
        unit = 10 ** math.floor(math.log10(raw))
        spacing = next(factor * unit for factor in (1, 2, 5, 10) if factor * unit >= raw)
        # Ticks must sit on actual observations, not half-way between candles.
        start = math.ceil(low / spacing) * spacing
        values = [start + i * spacing for i in range(max(0, math.floor((high - start) / spacing) + 1))]
        fallback = round((low + high) / 2)
        if len(values) < 2:
            values = [fallback] if low <= fallback <= high else []
        return [(spacing, values)]

    def tickStrings(self, values, scale, spacing):
        result = []
        short_range = False
        if self.times:
            left = self.times[max(0, min(len(self.times) - 1, int(self.range[0])))]
            right = self.times[max(0, min(len(self.times) - 1, int(self.range[1])))]
            left = datetime.fromisoformat(left) if isinstance(left, str) else left
            right = datetime.fromisoformat(right) if isinstance(right, str) else right
            short_range = 0 < (right - left).total_seconds() < 3600 and left.date() == right.date()
        for value in values:
            i = int(value)
            if 0 <= i < len(self.times):
                dt = self.times[i]
                if isinstance(dt, str):
                    dt = datetime.fromisoformat(dt)
                result.append(dt.strftime("%H:%M:%S") if short_range else (
                    dt.strftime("%m/%d %H:%M") if dt.hour != 15 else dt.strftime("%m/%d")))
            else:
                result.append("")
        return result


class CompactValueAxis(pg.AxisItem):
    def tickValues(self, minVal, maxVal, size):
        if size < 60 and maxVal > minVal:
            return [(maxVal - minVal, [(minVal + maxVal) / 2])]
        return super().tickValues(minVal, maxVal, size)


class PriceChart(QtWidgets.QWidget):
    def __init__(self, title="行情 / 买卖点"):
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.heading = label(title, "muted")
        layout.addWidget(self.heading)
        self.axis = ObservationAxis(orientation="bottom")
        self.widget = pg.GraphicsLayoutWidget()
        self.widget.setBackground(DARK["surface"])
        self.plot = self.widget.addPlot(row=0, col=0, axisItems={"left": CompactValueAxis(orientation="left")})
        self.volume = self.widget.addPlot(row=1, col=0, axisItems={"bottom": self.axis,
                                            "left": CompactValueAxis(orientation="left")})
        self.volume.setMaximumHeight(80)
        self.volume.setXLink(self.plot)
        for plot in (self.plot, self.volume):
            plot.getAxis("left").setWidth(64)
            plot.getAxis("left").setStyle(tickFont=QtGui.QFont("Segoe UI", 8), autoExpandTextSpace=False)
        self.plot.hideAxis("bottom")
        self.plot.showGrid(x=True, y=True, alpha=.13)
        self.volume.showGrid(y=True, alpha=.12)
        self.plot.setMenuEnabled(False)
        self.volume.setMenuEnabled(False)
        self.candles = CandleItem()
        self.plot.addItem(self.candles)
        self.line = self.plot.plot(pen=pg.mkPen("#79b6ee", width=1.6))
        self.volumes = pg.BarGraphItem(x=[], height=[], width=.65, brush="#304e66", pen=None)
        self.volume.addItem(self.volumes)
        self.markers = pg.ScatterPlotItem(size=10, pen=None)
        self.plot.addItem(self.markers)
        self.cursor = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#a6bbc9", style=QtCore.Qt.PenStyle.DashLine))
        self.plot.addItem(self.cursor)
        self.cursor.hide()
        self.points = []
        layout.addWidget(self.widget)
        self.setMinimumHeight(180)

    def set_data(self, points, trades=(), symbol="", quote=False, *, meta=None):
        self.points = points
        self.axis.times = [p["time"] for p in points]
        self.axis.picture = None
        self.axis.update()
        from astock.data_identity import origin_label, source_summary
        identity = f'{origin_label(meta)} · ' if meta else ''
        self.heading.setWordWrap(True)
        self.heading.setText(f"{identity}{symbol}  ·  {'报价快照' if quote else 'K 线'}  ·  {len(points)} 个观察值")
        self.heading.setToolTip(source_summary(meta) if meta else '')
        self.candles.set_data([] if quote else points)
        self.candles.setVisible(bool(points) and not quote)
        self.line.setVisible(quote)
        self.line.setData(list(range(len(points))) if quote else [], [p["close"] for p in points] if quote else [])
        self.volumes.setOpts(x=list(range(len(points))), height=[p["volume"] for p in points])
        lookup = {p["time"]: i for i, p in enumerate(points)}
        spots = []
        for t in trades:
            if t.symbol == symbol and t.time in lookup:
                spots.append({"pos": (lookup[t.time], float(t.price)), "symbol": "t1" if t.side == "BUY" else "t",
                              "brush": "#f07983" if t.side == "BUY" else "#53c6aa"})
        self.markers.setData(spots)
        self.plot.enableAutoRange()
        self.volume.enableAutoRange()

    def locate(self, at):
        i = next((i for i, point in enumerate(self.points) if point["time"] == at), None)
        if i is None:
            self.cursor.hide()
            return False
        self.cursor.setPos(i)
        self.cursor.show()
        self.plot.setXRange(max(0, i - 20), min(len(self.points), i + 20), padding=.02)
        return True

    def theme(self, name):
        c = DARK if name == "dark" else LIGHT
        self.widget.setBackground(c["surface"])
        for plot in (self.plot, self.volume):
            for side in ("left", "bottom"):
                plot.getAxis(side).setTextPen(c["muted"])
                plot.getAxis(side).setPen(c["line"])


class EquityChart(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.axis = ObservationAxis(orientation="bottom")
        self.widget = pg.GraphicsLayoutWidget()
        self.widget.setBackground(DARK["surface"])
        self.plot = self.widget.addPlot(row=0, col=0)
        self.plot.addLegend(offset=(10, 10))
        self.net = self.plot.plot(pen=pg.mkPen("#57d3b0", width=2), name="策略权益")
        self.benchmark = self.plot.plot(pen=pg.mkPen("#7d95c5", width=1.5, style=QtCore.Qt.PenStyle.DashLine), name="基准买入持有")
        self.plot.hideAxis("bottom")
        self.drawdown = self.widget.addPlot(row=1, col=0, axisItems={"bottom": self.axis})
        self.drawdown.setMaximumHeight(100)
        self.drawdown.setXLink(self.plot)
        # Reserve actual label room rather than relying on an exact floating-point
        # text bounding box. Native Qt at fractional DPI can otherwise clip every
        # equity tick; also align both panels' observation coordinates.
        for plot in (self.plot, self.drawdown):
            axis = plot.getAxis("left")
            axis.setWidth(82)
            axis.setStyle(tickFont=QtGui.QFont("Segoe UI", 9), autoExpandTextSpace=False)
        self.drawdown.setLabel("left", "回撤", units="%")
        self.drawdown.getAxis("left").enableAutoSIPrefix(False)
        self.dd = self.drawdown.plot(pen=pg.mkPen("#ef8292", width=1), fillLevel=0, brush=(239, 130, 146, 35))
        self.plot.showGrid(x=True, y=True, alpha=.15)
        layout.addWidget(self.widget)
        self.setMinimumHeight(200)

    def set_data(self, curve):
        self.axis.times = [x["time"] for x in curve]
        self.axis.picture = None
        self.axis.update()
        self.net.setData([p["equity"] for p in curve])
        self.benchmark.setData([p["benchmark"] for p in curve])
        self.dd.setData([-100 * p["drawdown"] for p in curve])

    def theme(self, name):
        c = DARK if name == "dark" else LIGHT
        self.widget.setBackground(c["surface"])
        for p in (self.plot, self.drawdown):
            for side in ("left", "bottom"):
                p.getAxis(side).setTextPen(c["muted"])
                p.getAxis(side).setPen(c["line"])
        self.drawdown.setLabel("left", "回撤", units="%", color=c["muted"])
