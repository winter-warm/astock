from PySide6 import QtCore, QtWidgets

from astock.model_browser import ModelBrowser
from astock.strategy import TEMPLATES


class StoreStub:
    def __init__(self):
        self.saved = [{"name": "我的模型", "parameters": {"fast": 5}}]

    def strategies(self):
        return self.saved


class WindowStub:
    def __init__(self):
        self.store = StoreStub()
        self.calls = []
        self.allow_open = True

    def open_strategy_editor(self, *key):
        self.calls.append(("edit", key))
        return self.allow_open

    def switch_workspace(self, index):
        self.calls.append(("navigate", index))


def test_saved_model_selection_survives_refresh_and_name_filter(qtbot):
    window = WindowStub()
    browser = ModelBrowser(window)
    qtbot.addWidget(browser)
    browser.models.selectRow(len(TEMPLATES))
    window.store.saved.insert(0, {"name": "另一个模型", "parameters": {}})
    browser.refresh()
    assert browser.key_at(browser.models.currentRow()) == ("saved", "我的模型")
    browser.search.setText("我的")
    visible = [row for row in range(browser.models.rowCount()) if not browser.models.isRowHidden(row)]
    assert len(visible) == 1
    assert browser.key_at(visible[0]) == ("saved", "我的模型")
    browser.search.setText("没有匹配的名字")
    assert browser.models.currentRow() == -1
    assert "没有匹配" in browser.summary.text()


def test_row_buttons_dispatch_selected_model_before_backtest(qtbot):
    window = WindowStub()
    browser = ModelBrowser(window)
    qtbot.addWidget(browser)
    row = len(TEMPLATES)
    buttons = browser.models.cellWidget(row, 2).findChildren(QtWidgets.QToolButton)
    qtbot.mouseClick(buttons[1], QtCore.Qt.MouseButton.LeftButton)
    assert window.calls == [("edit", ("saved", "我的模型")), ("navigate", 1)]
    window.calls.clear()
    window.allow_open = False
    qtbot.mouseClick(buttons[1], QtCore.Qt.MouseButton.LeftButton)
    assert window.calls == [("edit", ("saved", "我的模型"))]


def test_same_name_template_and_saved_model_keep_distinct_identity(qtbot):
    window = WindowStub()
    name = next(iter(TEMPLATES))
    window.store.saved = [{"name": name, "parameters": {}}]
    browser = ModelBrowser(window)
    qtbot.addWidget(browser)
    browser.open_row(0)
    browser.open_row(len(TEMPLATES))
    assert window.calls == [("edit", ("template", name)), ("edit", ("saved", name))]
