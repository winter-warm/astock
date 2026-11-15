"""Exercise the editor/header buttons and verify their effect on the current work."""
from copy import deepcopy

import pytest
from PySide6 import QtCore, QtWidgets

from astock.backtest_setup import BacktestSetup
from astock.data_jobs import DataJobs
from astock.window import MainWindow


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(DataJobs, 'start', lambda *a, **k: 'entrypoint-preview')
    widget = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(widget)
    widget.show()
    return widget


def test_strategy_reference_keeps_editor_draft_parameters_and_learning(window, qtbot):
    window.editor.appendPlainText('# 保留未保存草稿')
    window.parameters['fast'].setValue(7)
    code = window.editor.toPlainText()
    course = window.course_library.current['id']
    learning = deepcopy(window.course_library.state)
    saved = window.store.strategies()
    qtbot.mouseClick(window.strategy_dialog.api_button, QtCore.Qt.MouseButton.LeftButton)
    dialog = window.strategy_api_dialog
    assert dialog.isVisible() and not dialog.isModal()
    assert window.pages.currentIndex() == 0
    assert 'ctx.order(symbol, side, quantity, price' in dialog.findChild(QtWidgets.QTextBrowser).toPlainText()
    box = dialog.findChild(QtWidgets.QDialogButtonBox)
    qtbot.mouseClick(box.button(QtWidgets.QDialogButtonBox.StandardButton.Close), QtCore.Qt.MouseButton.LeftButton)
    assert not dialog.isVisible()
    qtbot.mouseClick(window.strategy_dialog.api_button, QtCore.Qt.MouseButton.LeftButton)
    assert window.strategy_api_dialog is dialog and dialog.isVisible()
    assert window.editor.toPlainText() == code
    assert window.parameter_values()['fast'] == 7
    assert window.course_library.current['id'] == course
    assert window.course_library.state == learning
    assert window.store.strategies() == saved
    assert not window.states and not window.start_pending


@pytest.mark.parametrize('save', [False, True])
def test_quote_settings_can_select_bars_and_apply_only_on_save(window, qtbot, save):
    window._select_demo('quote')
    window.go_backtest()
    original_data = window.dataset_combo.currentData()
    original_capital = window.capital.value()
    original_code = window.editor.toPlainText()
    bar = next(meta for meta in window.datasets if meta['kind'] == 'bar')
    observations = []

    def interact():
        dialog = QtWidgets.QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, BacktestSetup)
            assert dialog.selected_meta()['kind'] == 'quote'
            assert '完整录制区间' in dialog.selection_note.text()
            assert not dialog.dates[0].isEnabled()
            dialog.dataset.setCurrentIndex(dialog.dataset.findData(bar['id']))
            assert dialog.dates[0].isEnabled()
            dialog.capital.setValue(234000)
            button = QtWidgets.QDialogButtonBox.StandardButton.Save if save else QtWidgets.QDialogButtonBox.StandardButton.Cancel
            qtbot.mouseClick(dialog.actions.button(button), QtCore.Qt.MouseButton.LeftButton)
            observations.append(True)
        finally:
            if dialog and dialog.isVisible():
                dialog.reject()

    QtCore.QTimer.singleShot(0, interact)
    qtbot.mouseClick(window.backtest_settings_button, QtCore.Qt.MouseButton.LeftButton)
    assert observations == [True]
    assert window.dataset_combo.currentData() == (bar['id'] if save else original_data)
    assert window.capital.value() == (234000 if save else original_capital)
    assert window.backtest_start_button.text() == ('开始回测' if save else '开始回放')
    assert window.editor.toPlainText() == original_code
    assert not window.states and not window.start_pending


@pytest.mark.parametrize('boundary', ['minimum', 'maximum'])
def test_settings_capital_boundary_round_trips_without_silent_clamping(window, qtbot, boundary):
    window.go_backtest()
    amounts = []

    def interact():
        dialog = QtWidgets.QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, BacktestSetup)
            assert dialog.capital.minimum() == window.capital.minimum()
            assert dialog.capital.maximum() == window.capital.maximum()
            dialog.capital.setValue(getattr(dialog.capital, boundary)())
            amounts.append(dialog.capital.value())
            qtbot.mouseClick(dialog.actions.button(QtWidgets.QDialogButtonBox.StandardButton.Save),
                             QtCore.Qt.MouseButton.LeftButton)
        finally:
            if dialog and dialog.isVisible():
                dialog.reject()

    QtCore.QTimer.singleShot(0, interact)
    qtbot.mouseClick(window.backtest_settings_button, QtCore.Qt.MouseButton.LeftButton)
    assert amounts == [getattr(window.capital, boundary)()]
    assert window.capital.value() == amounts[0]
    assert not window.states and not window.start_pending


@pytest.mark.parametrize('page', [0, 1, 2, 3, 4, 5])
def test_view_menu_hints_and_reset_keep_current_workspace(window, page):
    window.switch_workspace(page)
    window.editor_settings.setCurrentIndex(0)
    code = window.editor.toPlainText()
    view = next(action.menu() for action in window.menuBar().actions() if action.text() == '视图')
    hints = next(action for action in view.actions() if action.text() == '显示 / 隐藏教学提示')
    hints.trigger()
    assert window.help_panel.isVisible()
    assert window.pages.currentIndex() == page
    hints.trigger()
    assert not window.help_panel.isVisible()
    assert window.editor_settings.currentIndex() == 1
    window.library_dock.show()
    window.bottom_dock.show()
    next(action for action in view.actions() if action.text() == '恢复默认布局').trigger()
    assert window.pages.currentIndex() == page
    assert not window.library_dock.isVisible()
    assert window.parameter_dock.isVisible() == (page == 2)
    assert window.bottom_dock.isVisible() == (page == 2)
    if page == 0:
        assert window.parameter_scroll.isVisible()
        assert window.strategy_dialog.isAncestorOf(window.parameter_scroll)
        assert '写策略页面右侧' in window.parameter_dock.toggleViewAction().toolTip()
    assert window.editor.toPlainText() == code
    assert not window.states and not window.start_pending
