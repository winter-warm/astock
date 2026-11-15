"""Primary workflows are reachable without first discovering a secondary window."""
from PySide6 import QtCore, QtWidgets

from astock.window import MainWindow


def test_one_navigation_and_default_inline_editor(qtbot, tmp_path):
    w = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(w)
    w.show()
    assert w.pages.currentIndex() == 0
    assert w.editor.isVisible()
    assert w.pages.currentWidget().isAncestorOf(w.editor)
    assert w.editor.window() is w
    assert w.findChild(QtWidgets.QToolBar, 'workspaceNavigation') is None
    assert w.toolBarArea(w.navigation_rail) == QtCore.Qt.ToolBarArea.LeftToolBarArea
    expected = {0: '写策略', 1: '历史回测', 2: '模拟交易', 3: '量化课程', 4: '账户与记录', 5: '数据中心'}
    assert {w.nav_group.id(b): b.text() for b in w.nav_group.buttons()} == expected
    for control in (w.new_strategy_button, w.template_button, w.save_strategy_button):
        assert control.isVisible()
    w.close()


def test_data_page_defaults_to_historical_data_and_selects_without_run(qtbot, tmp_path, monkeypatch):
    w = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(w)
    w.show()
    calls = []
    monkeypatch.setattr(w, 'start_run', lambda *a, **k: calls.append('run'))
    w.nav_group.button(5).click()
    assert w.data_market_tabs.currentIndex() == 0
    assert w.data_overview_table.isVisible()
    assert w.data_overview_table.rowCount() == len(w.datasets)
    last = w.data_overview_table.rowCount() - 1
    w.data_overview_table.selectRow(last)
    assert w.dataset_combo.currentData() == w.data_overview_table.item(last, 0).data(QtCore.Qt.ItemDataRole.UserRole)
    assert calls == []
    w.close()


def test_switching_workspaces_preserves_draft_and_does_not_run_or_save(qtbot, tmp_path, monkeypatch):
    w = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(w)
    w.show()
    w.editor.appendPlainText('# still unsaved')
    code = w.editor.toPlainText()
    w.parameters['fast'].setValue(8)
    calls = []
    with monkeypatch.context() as patches:
        patches.setattr(w, 'save_strategy', lambda *a, **k: calls.append('save'))
        patches.setattr(w, 'start_run', lambda *a, **k: calls.append('run'))
        w.strategy_dialog.backtest_button.click()
        assert w.pages.currentIndex() == 1
        for index in (2, 4, 5, 3, 0):
            w.nav_group.button(index).click()
        assert calls == []
        assert w.editor.toPlainText() == code
        assert w.parameters['fast'].value() == 8
        assert w.strategy_dialog.isAncestorOf(w.parameter_scroll)
    w.close()
