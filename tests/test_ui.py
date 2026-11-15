import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6 import QtCore

from astock.strategy import TEMPLATES
from astock.window import MainWindow


@pytest.fixture
def window(qtbot, tmp_path):
    w = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(w)
    w.resize(1280, 720)
    w.show()
    return w


def test_first_use_has_offline_data_and_relevant_parameter_help(window):
    assert len(window.datasets) == 2
    assert all(m["demo"] for m in window.datasets)
    assert window.parameters["fast"].value() == 5
    assert "观察值" in window.parameters["fast"].toolTip()
    assert "教学" in window.data_badge.text()


def test_panel_title_controls_can_float_redock_and_reopen(window, qtbot):
    from PySide6 import QtWidgets
    dock = window.library_dock
    detach, close = dock.titleBarWidget().findChildren(QtWidgets.QToolButton)
    qtbot.mouseClick(detach, QtCore.Qt.MouseButton.LeftButton)
    assert dock.isFloating()
    qtbot.mouseClick(detach, QtCore.Qt.MouseButton.LeftButton)
    assert not dock.isFloating()
    qtbot.mouseClick(close, QtCore.Qt.MouseButton.LeftButton)
    assert not dock.isVisible()
    dock.toggleViewAction().trigger()
    assert dock.isVisible()


def test_scrolling_analysis_does_not_hide_current_mode_or_main_controls(window, qtbot):
    window.switch_workspace(1)
    window.resize(1280, 720)
    qtbot.wait(100)
    window.workspace_scroll.verticalScrollBar().setValue(window.workspace_scroll.verticalScrollBar().maximum())
    assert window.mode_badge.isVisible() and window.backtest_start_button.isVisible()
    assert not window.workspace_scroll.isAncestorOf(window.mode_badge)


def test_equity_lesson_preserves_editor_and_explains_cash_vs_receivable(window, qtbot):
    from queue import Queue
    from astock.engine import Run
    from astock.strategy import parameter_schema
    window.editor.setPlainText(window.editor.toPlainText() + "\n# keep my work")
    window.show_lesson(2)
    window.switch_workspace(3)
    qtbot.mouseClick(window.equity_lesson_button, QtCore.Qt.MouseButton.LeftButton)
    assert any("keep my work" in row["code"] for row in window.store.strategies())
    assert window.mode_combo.currentData() == "backtest" and window.active_id is None
    code = window.editor.toPlainText()
    params = {key: spec["default"] for key, spec in parameter_schema(code).items()}
    run = Run({"mode": "backtest", "dataset": window.dataset_combo.currentData(), "code": code,
               "parameters": params, "autoplay": False}, window.root, Queue())
    try:
        for _ in range(3):
            run.step()
        state = run.message()
        window.states[run.id], window.active_id = state, run.id
        window.display_run(state)
        assert "数据区间（北京时间）" in window.backtest_range.text()
        assert "已读取 3/" in window.backtest_progress.text()
        assert window.activity_orders.model().rowCount() == len(state["snapshot"]["orders"])
        assert window.activity_trades.model().rowCount() == len(state["snapshot"]["trades"])
        assert "应收分红 100.00" in window.equity_note.text()
        assert "累计到账 0.00" in window.equity_note.text()
        assert window.equity_table.model().rowCount() == 1
        assert window.positions_table.item(0, 2).text() == "100"
        while run.status != "COMPLETED":
            run.step()
        state = run.message()
        window.states[run.id] = state
        window.display_run(state)
        assert "应收分红 0.00" in window.equity_note.text()
        assert "累计到账 100.00" in window.equity_note.text()
        assert window.equity_table.model().rowCount() == 2
        assert window.positions_table.item(0, 2).text() == "200"
        assert window.activity_logs.toPlainText() == window.log_view.toPlainText()
        window.activity_trades.selectRow(0)
        assert window.trade_context["trade_id"] == state["snapshot"]["trades"][0].id
        assert state["snapshot"]["trades"][0].time.strftime("%Y-%m-%d") in window.trade_explanation.text()
        qtbot.wait(100)
        assert window.equity_table.viewport().height() >= 2 * window.equity_table.verticalHeader().defaultSectionSize()
        window.trades_table.selectRow(0)
        qtbot.wait(100)
        viewport = window.workspace_scroll.viewport()
        top = window.result_chart.mapTo(viewport, QtCore.QPoint(0, 0)).y()
        assert 0 <= top and top + window.result_chart.height() <= viewport.height()
        state["snapshot"]["legacy_equity_unverified"] = True
        window.display_run(state)
        assert "旧版本权益流水不完整" in window.equity_note.text()
    finally:
        if run.host:
            run.stop()


def test_switching_template_saves_user_work(window):
    code = window.editor.toPlainText() + "\n# 我的修改\n"
    window.editor.setPlainText(code)
    window.parameters["fast"].setValue(8)
    window.load_template("区间突破")
    saved = next(x for x in window.store.strategies() if x["name"] == "双均线趋势")
    assert saved["code"] == code
    assert saved["parameters"]["fast"] == 8
    assert "lookback" in window.parameters


def test_syntax_error_has_readable_feedback_and_location(window, monkeypatch):
    messages = []
    monkeypatch.setattr(window, "error", lambda text, **kwargs: messages.append(text))
    window.editor.setPlainText("# line 1\ndef broken(:\n    pass")
    window.rebuild_parameters()
    assert messages
    assert window.editor.textCursor().blockNumber() == 1


def test_teaching_actions_select_correct_modes_and_progress_persists(window):
    window.show_lesson(0)
    window.lesson_do()
    assert window.mode_combo.currentData() == "replay"
    window.complete_lesson()
    assert window.store.setting("lessons_completed") == [0]
    window.show_lesson(3)
    window.lesson_do()
    assert window.pages.currentIndex() == 2
    assert window.mode_combo.currentData() == "live"


def test_toggle_theme_and_docks_can_be_restored(window):
    window.toggle_theme()
    assert window.store.setting("theme") == "light"
    window.library_dock.hide()
    window.reset_layout()
    assert not window.library_dock.isVisible()
    assert not window.bottom_dock.isVisible()
    assert not window.parameter_dock.isVisible()
    assert window.parameter_scroll.isVisible()
    assert window.strategy_dialog.isAncestorOf(window.parameter_scroll)


def test_double_start_does_not_create_duplicate_accounts(window):
    window.start_run()
    window.start_run()
    assert window.start_pending
    assert not window.start_button.isEnabled()
    assert window.engine_commands.get(timeout=1)["op"] == "start"
    from queue import Empty
    with pytest.raises(Empty):
        window.engine_commands.get(timeout=.05)


def test_large_font_and_small_window_keep_primary_controls_reachable(window, qtbot):
    from PySide6 import QtWidgets
    window.resize(1280, 720)
    window.open_strategy_editor()
    window.editor_settings.setCurrentIndex(1)
    qtbot.wait(100)
    assert window.width() <= 1280
    assert not window.start_button.isVisible()
    backtest_button = next(b for b in window.strategy_dialog.findChildren(QtWidgets.QPushButton)
                           if b.text() == "去回测")
    assert backtest_button.isVisible() and backtest_button.width() > 30
    assert window.editor.isVisible()
    assert window.editor.viewport().width() > 100
    target = window.parameters["fast"]
    window.parameter_scroll.ensureWidgetVisible(target)
    qtbot.wait(30)
    viewport = window.parameter_scroll.viewport()
    assert target.isVisible()
    assert viewport.rect().contains(QtCore.QRect(target.mapTo(viewport, QtCore.QPoint(0, 0)), target.size()))


def test_keyboard_save_and_runtime_source_are_separate(window, qtbot):
    window.open_strategy_editor()
    window.editor.setPlainText(TEMPLATES["双均线趋势"]["code"] + "\n# keyboard save")
    window.editor.setFocus()
    qtbot.keyClick(window.editor, QtCore.Qt.Key.Key_S, QtCore.Qt.KeyboardModifier.ControlModifier)
    qtbot.wait(100)
    assert any("keyboard save" in x["code"] for x in window.store.strategies())


@pytest.mark.parametrize("height", [450, 550])
def test_high_scaling_small_screen_uses_reachable_compact_layout(window, qtbot, height):
    # Small screens with 150% scaling; overflow remains scrollable.
    window.switch_workspace(0)
    window.fit_initial_layout(900, height)
    qtbot.wait(100)
    assert window.width() <= 900
    assert window.height() <= height
    assert not window.library_dock.isVisible()
    assert not window.parameter_dock.isVisible()
    assert not window.bottom_dock.isVisible()
    assert not window.start_button.isVisible()
    assert window.editor.isVisible()
    assert window.editor.viewport().width() > 100
    new_model = window.new_strategy_button
    assert new_model.isVisible() and new_model.width() > 60
    assert not window.parameter_dock.toggleViewAction().isEnabled()
    window.parameter_dock.toggleViewAction().trigger()
    assert not window.parameter_dock.isVisible()
    assert window.strategy_dialog.isAncestorOf(window.parameter_scroll)
    window.switch_workspace(1)
    assert window.parameter_dock.toggleViewAction().isEnabled()
    window.parameter_dock.toggleViewAction().trigger()
    assert window.parameter_dock.isVisible()
    assert window.parameter_dock.widget() is window.parameter_scroll


def test_quote_age_keeps_advancing_without_new_messages(window, monkeypatch):
    from datetime import datetime, timedelta
    from astock.domain import CN, Quote, dec
    from astock import window as window_module
    timestamp = datetime(2026, 11, 12, 10, tzinfo=CN)
    window.quotes = {"600000.SH": Quote("600000.SH", timestamp, timestamp, dec(10))}
    window.market_metrics = {"status": "已连接", "interval": 5.0}
    monkeypatch.setattr(window_module, "now_cn", lambda: timestamp + timedelta(seconds=2))
    window.refresh_market_status()
    assert window.quote_table.item(0, 5).text() == "2.0"
    monkeypatch.setattr(window_module, "now_cn", lambda: timestamp + timedelta(seconds=30))
    window.refresh_market_status()
    assert window.quote_table.item(0, 5).text() == "30.0"
    assert "过期" in window.market_badge.text()
    assert "30.0s" in window.market_status.text()
    window.market_metrics = {"status": "连接失败，10 秒后重试", "message": "timeout"}
    window.refresh_market_status()
    assert "重试" in window.market_badge.text()
    assert "timeout" in window.market_badge.toolTip()


def test_account_and_market_status_remain_visible_without_bottom_panel(window):
    from queue import Queue
    from astock.engine import Run
    run = Run({"mode": "manual", "name": "练习", "symbols": ["600000.SH"]}, window.root, Queue())
    window.display_run(run.message())
    window.fit_initial_layout(900, 450)
    assert not window.bottom_dock.isVisible()
    assert window.account_status.isVisible()
    assert run.id[:6] in window.account_status.text()
    assert window.market_badge.isVisible()
    run.stop()


def test_first_single_step_creates_account_and_advances_once(window, qtbot):
    window._select_demo("quote")
    window.step_run()
    request = window.engine_commands.get(timeout=1)
    assert request["op"] == "start" and request["autoplay"] is False
    window.output.put({"type": "run_created", "id": "step-test"})
    qtbot.waitUntil(lambda: window.active_id == "step-test", timeout=2000)
    assert window.engine_commands.get(timeout=1) == {"op": "step", "id": "step-test"}
    assert not window.step_after_start


def test_live_mode_does_not_offer_single_step(window):
    window.mode_combo.setCurrentIndex(2)
    assert not window.step_action.isEnabled()
    window.step_run()
    assert not window.start_pending
    assert "由行情驱动" in window.statusBar().currentMessage()
    window._select_demo("quote")
    assert window.step_action.isEnabled()


def test_custom_indicator_values_are_visible_in_ui_and_report(window):
    from queue import Queue
    from astock.engine import Run
    from astock.reports import export_report
    run = Run({"mode": "manual", "symbols": ["600000.SH"]}, window.root, Queue())
    run.log("我的交易解释", {"均线": 12.34, "条件": "<price>"})
    state = run.message()
    window.display_run(state)
    assert "均线=12.34" in window.log_view.toPlainText()
    report = export_report(window.root, state).read_text(encoding="utf-8")
    assert "我的交易解释" in report and "均线=12.34" in report
    assert "&lt;price&gt;" in report and "<price>" not in report
    run.stop()


def test_equity_chart_short_height_keeps_readable_numeric_ticks(window, qtbot):
    from datetime import datetime, timedelta
    from PySide6 import QtGui
    from astock.domain import CN
    chart = window.equity_chart
    window.switch_workspace(1)
    window.result_tabs.setCurrentWidget(chart)
    chart.set_data([{"time": datetime(2026, 11, 12, 10, tzinfo=CN) + timedelta(seconds=i),
                     "equity": 99500 + i * 20, "benchmark": 100000 + i * 10, "drawdown": .002}
                    for i in range(60)])
    chart.setFixedHeight(225)
    qtbot.wait(100)
    chart.grab()  # Exercise painting and font metrics before examining visible labels.
    canvas = QtGui.QImage(800, 300, QtGui.QImage.Format.Format_ARGB32)
    painter = QtGui.QPainter(canvas)
    try:
        axis = chart.plot.getAxis("left")
        _, _, texts = axis.generateDrawSpecs(painter)
        assert len(texts) >= 2
        assert all(text[-1].replace(".", "").isdigit() for text in texts)
    finally:
        painter.end()


def test_live_input_capture_count_and_replay_limit_are_explained(window):
    from queue import Queue
    from astock.engine import Run
    run = Run({"mode": "manual", "symbols": ["600000.SH"]}, window.root, Queue())
    window.display_run(run.message())
    text = window.live_manifest_text.toPlainText()
    assert "自动留存 0 条" in text
    assert "手动下单、暂停和撤单不自动重演" in text
    run.stop()


def test_trade_detail_chart_does_not_overlap_explanation_in_short_window(window, qtbot):
    window.resize(1280, 720)
    window.switch_workspace(1)
    window.result_tabs.setCurrentWidget(window.trade_page)
    window.trade_explanation.setText("T000001 · 2026-11-12 09:31:40 · 快线高于慢线，满足买入条件")
    qtbot.wait(100)
    chart = window.result_chart.geometry()
    explanation = window.trade_explanation.geometry()
    assert chart.bottom() < explanation.top()
    assert explanation.bottom() < window.result_tabs.currentWidget().height()
