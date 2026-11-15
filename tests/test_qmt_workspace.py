from PySide6 import QtCore, QtWidgets

from astock.qmt_learning import COURSES
from astock.qmt_workspace import name_model
from astock.window import MainWindow


def test_navigation_preserves_editor_and_practice_and_quiz_progress(qtbot, tmp_path):
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.editor.appendPlainText("# unsaved work")
    code = window.editor.toPlainText()
    for index in (4, 5, 0, 1, 2, 3):
        window.nav_group.button(index).click()
        assert window.pages.currentIndex() == index
    assert window.editor.toPlainText() == code
    course = window.migration_course
    course.answers.setCurrentIndex(0)
    course.check()
    assert window.store.setting("qmt_course_v1") is None
    course.answers.setCurrentIndex(COURSES[0]["answer"] + 1)
    course.check()
    assert window.store.setting("qmt_course_v1")["orientation"]
    assert not window.completed
    window.close()
    reopened = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(reopened)
    assert reopened.migration_course.progress["orientation"]
    assert reopened.pages.currentIndex() == 0
    reopened.close()


def test_copy_model_preserves_unsaved_original_and_parameters(qtbot, tmp_path, monkeypatch):
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    original = window.current_template
    window.editor.appendPlainText("# keep this change")
    window.parameters["fast"].setValue(7)
    monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a: ("试验副本", True))
    name_model(window)
    saved = {s["name"]: s for s in window.store.strategies()}
    assert saved[original]["code"] == saved["试验副本"]["code"]
    assert saved["试验副本"]["parameters"]["fast"] == 7
    window.close()


def test_new_model_runs_in_real_strategy_process(qtbot, tmp_path, monkeypatch):
    from queue import Queue
    from astock.engine import Run
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a: ("空白练习", True))
    name_model(window, copy=False)
    run = Run({"mode": "backtest", "dataset": window.dataset_combo.currentData(),
               "code": window.editor.toPlainText(), "parameters": {}, "initial": 100000}, tmp_path, Queue())
    try:
        while run.status == "RUNNING":
            run.step()
        assert run.status == "COMPLETED"
        assert not run.broker.trades
    finally:
        if run.host:
            run.host.close()
        window.close()


def test_backtest_entry_corrects_live_mode_and_rejects_quote_data(qtbot, tmp_path, monkeypatch):
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    requests = []
    monkeypatch.setattr(window, "start_run", lambda **kwargs: requests.append(kwargs))
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("live"))
    window.start_backtest()
    assert requests == [{"mode": "backtest"}]
    assert window.mode_combo.currentData() == "backtest"
    errors = []
    monkeypatch.setattr(window, "error", errors.append)
    window._select_demo("quote")
    window.start_backtest()
    assert len(requests) == 1 and errors
    window.close()


def test_expanded_analysis_and_practice_navigation_restore_context(qtbot, tmp_path):
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.show()
    window.switch_workspace(1)
    window.library_dock.show()
    qtbot.wait(50)
    previous = bytes(window.saveState())
    window.toggle_analysis_layout()
    assert not window.bottom_dock.isVisible()
    window.toggle_analysis_layout()
    assert window.analysis_layout is None
    assert bytes(window.saveState()) == previous
    window.toggle_analysis_layout()
    window.switch_workspace(0)
    assert window.analysis_layout is None
    assert not window.library_dock.isVisible()
    assert not window.metrics_panel.isVisible()
    window.learning_sections.setCurrentIndex(1)
    window.open_practice()
    assert window.pages.currentIndex() == 3
    assert window.learning_sections.currentIndex() == 0
    window.close()


def test_strategy_picker_returns_to_inline_editor_and_preserves_unsaved_changes(qtbot, tmp_path):
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.show()
    window.switch_workspace(0)
    browser = window.model_browser
    assert window.pages.currentWidget() is window.strategy_dialog
    assert window.editor.isVisible()
    assert not browser.models.isVisible()
    window.open_strategy_library()
    assert browser.models.isVisible()
    buttons = browser.models.cellWidget(0, 2).findChildren(QtWidgets.QToolButton)
    qtbot.mouseClick(buttons[0], QtCore.Qt.MouseButton.LeftButton)
    assert window.strategy_dialog.isVisible() and window.editor.isVisible()
    assert window.strategy_dialog.isAncestorOf(window.editor)
    assert not window.strategy_library_dialog.isVisible()
    code = window.editor.toPlainText() + "\n# keep across workspace navigation"
    window.editor.setPlainText(code)
    window.parameters["fast"].setValue(9)
    window.switch_workspace(2)
    assert not window.strategy_dialog.isVisible()
    assert window.editor.toPlainText() == code
    assert window.parameter_dock.widget() is window.parameter_scroll
    window.open_strategy_editor()
    assert window.editor.toPlainText() == code
    assert window.parameters["fast"].value() == 9
    assert window.strategy_dialog.isAncestorOf(window.parameter_scroll)
    window.save_strategy()
    window.switch_workspace(1)
    window.open_strategy_editor("saved", window.current_template)
    assert window.editor.toPlainText() == code
    assert window.parameters["fast"].value() == 9
    window.close()


def test_editor_settings_tabs_reach_actual_controls(qtbot, tmp_path):
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.show()
    window.open_strategy_editor()
    assert [window.editor_settings.tabText(i) for i in range(window.editor_settings.count())] == [
        "基本信息", "参数设置", "回测参数", "操作指引"]
    targets = (window.dataset_combo, window.parameters["fast"], window.slippage, window.context_help)
    for index, target in enumerate(targets):
        window.editor_settings.setCurrentIndex(index)
        window.parameter_scroll.ensureWidgetVisible(target)
        qtbot.wait(30)
        assert target.isVisible()
        viewport = window.parameter_scroll.viewport()
        point = target.mapTo(viewport, QtCore.QPoint(0, 0))
        assert viewport.rect().contains(QtCore.QRect(point, target.size()))
    window.close()


def test_backtest_overview_uses_actual_account_and_opens_trade_details(qtbot, tmp_path):
    from queue import Queue
    from astock.engine import Run
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.show()
    window.switch_workspace(1)
    assert window.result_tabs.currentWidget() is window.backtest_overview
    run = Run({"mode": "backtest", "dataset": window.dataset_combo.currentData(),
               "code": window.editor.toPlainText(), "parameters": window.parameter_values(),
               "initial": 100000}, tmp_path, Queue())
    try:
        while run.status == "RUNNING":
            run.step()
        assert run.status == "COMPLETED" and run.broker.trades
        state = run.message()
        window.states[run.id], window.active_id = state, run.id
        window.display_run(state)
        overview = window.backtest_overview
        stats = state["result"]["statistics"]
        assert overview.performance.item(0, 1).text() == f"{stats['equity']:,.2f}"
        assert overview.performance.item(1, 1).text() == f"{stats['return']:.2%}"
        before = [overview.performance.item(row, 1).text() for row in range(8)]
        assert overview.symbol_combo.count() > 1
        overview.symbol_combo.setCurrentIndex(1)
        symbol = overview.symbol_combo.currentText()
        assert window.chart_symbol.currentText() == symbol
        assert overview.price_chart.points == state["result"]["prices"][symbol]
        assert [overview.performance.item(row, 1).text() for row in range(8)] == before
        traded_symbol = state["snapshot"]["trades"][0].symbol
        overview.symbol_combo.setCurrentText(traded_symbol)
        overview.trades.selectRow(0)
        assert window.result_tabs.currentWidget() is window.trade_page
        assert window.trade_context["symbol"] == traded_symbol
        assert window.trade_context["trade_id"] == overview.trades.current_record().id
        window.result_tabs.setCurrentWidget(overview)
        overview.show_diagnostics()
        assert window.result_tabs.currentWidget() is window.diagnostics
        assert "分月表现" in window.diagnostics.toPlainText()
    finally:
        if run.host:
            run.host.close()
        window.close()
