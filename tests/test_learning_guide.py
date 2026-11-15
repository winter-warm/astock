import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from queue import Queue

import pytest
from PySide6 import QtCore

from astock.engine import Run
from astock.window import MainWindow


@pytest.fixture
def window(qtbot, tmp_path):
    window = MainWindow(tmp_path, start_workers=False)
    window.engine_commands = Queue()
    qtbot.addWidget(window)
    window.resize(1280, 760)
    window.show()
    return window


def request(window):
    while True:
        message = window.engine_commands.get_nowait()
        if message["op"] == "start":
            return message


def display(window, run):
    window.start_pending = False
    window.active_id = run.id
    state = run.message()
    window.states[run.id] = state
    window.learning.observe(state)
    window.display_run(state)
    return state


def test_reading_is_not_practice_and_glossary_cannot_mark_the_previous_lesson(window):
    window.complete_lesson()
    assert window.completed == {0}
    assert not any(window.learning.achieved(i) for i in range(4))
    window.show_glossary()
    assert not window.lesson_done_button.isVisible()
    window.show_api()
    assert not window.lesson_done_button.isVisible()
    window.show_lesson(0)
    assert window.lesson_done_button.isVisible()


def test_modified_parameters_survive_next_lesson_and_original_code_is_preserved(window):
    original = window.editor.toPlainText() + "\n# 我的研究不要覆盖\n"
    window.editor.setPlainText(original)
    window.parameters["fast"].setValue(7)
    window.learning.begin(1)
    name = window.current_template
    assert name.startswith("教学 · 双均线参数")
    saved = next(row for row in window.store.strategies() if row["name"] == "双均线趋势")
    assert saved["code"] == original and saved["parameters"]["fast"] == 7
    window.parameters["fast"].setValue(10)
    assert window.learning.steps(1) == {"loaded", "changed"}
    window.learning.act()
    assert window.learning.complete(1)
    window.learning.begin(2)
    job = request(window)
    assert job["parameters"]["fast"] == 10 and job["parameters"]["slow"] == 20
    assert job["name"] == name and job["learning"]["lesson"] == 2
    assert window.learning.steps(2) == set()


def test_invalid_or_reverted_parameters_do_not_earn_saved_step(window):
    window.learning.begin(1)
    window.parameters["fast"].setValue(30)
    window.save_strategy()
    assert "changed" not in window.learning.steps(1) and "saved" not in window.learning.steps(1)
    window.parameters["fast"].setValue(10)
    window.parameters["fast"].setValue(5)
    window.save_strategy()
    assert "saved" not in window.learning.steps(1)
    assert "默认" in window.guide_text.text()


def test_two_step_lesson_has_no_same_quote_fill_and_requires_trade_selection(window):
    window.learning.begin(0)
    window.learning.act()
    run = Run(request(window), window.root, Queue())
    try:
        display(window, run)
        run.step()
        first = display(window, run)
        assert len(first["snapshot"]["orders"]) == 1 and not first["snapshot"]["trades"]
        assert first["snapshot"]["orders"][0].active and first["frozen"] > 0
        assert window.learning.steps(0) == {"loaded", "order"}
        run.step()
        second = display(window, run)
        assert len(second["snapshot"]["trades"]) == 1
        assert second["snapshot"]["trades"][0].time > first["snapshot"]["orders"][0].created
        assert not window.learning.complete(0)
        window.learning.act()
        window.trades_table.selectRow(0)
        assert window.learning.complete(0)
        assert "等待下一条" in window.context_help.text()
        assert window.trade_context["points"]
    finally:
        run.stop()


def test_offline_live_lesson_keeps_network_off_and_cancels_pending_order(window):
    window.learning.begin(3, offline=True)
    window.learning.act()
    job = request(window)
    assert job["mode"] == "replay" and job["learning"]["route"] == "offline"
    run = Run(job, window.root, Queue())
    try:
        run.step()
        display(window, run)
        assert len(run.broker.orders) == 2 and not run.broker.trades
        run.step()
        display(window, run)
        assert len(run.broker.trades) == 1 and sum(o.active for o in run.broker.orders) == 1
        assert run.broker.frozen_cash > 0
        window.learning.act()
        assert window.engine_commands.get_nowait()["op"] == "stop"
        run.stop()
        display(window, run)
        assert run.broker.frozen_cash == 0 and not any(o.active for o in run.broker.orders)
        assert window.learning.complete(3) and not window.connected and not window.quotes
        assert window.learning.records["3"]["route"] == "offline"
        assert "不代表" in window.guide_text.text()
        window.learning.begin(3)
        assert window.learning.achieved(3) and not window.learning.complete(3)
        assert window.learning.records["3"]["previous_completion"]["route"] == "offline"
        assert "quote" not in window.learning.steps(3)
    finally:
        run.stop()


def test_different_account_and_failed_trade_lookup_do_not_complete_practice(window):
    window.learning.begin(2)
    job = request(window)
    unrelated = Run({**job, "learning": {"attempt": "other"}}, window.root, Queue())
    try:
        window.learning.observe(unrelated.message())
        window.learning.reviewed_trade(unrelated.id, "fake")
        assert window.learning.steps(2) == set()
    finally:
        unrelated.stop()


def test_saved_progress_and_parameters_reopen_without_starting_strategy(window, qtbot):
    window.learning.begin(1)
    window.parameters["fast"].setValue(10)
    window.save_strategy()
    root = window.root
    window.close()
    reopened = MainWindow(root, start_workers=False)
    qtbot.addWidget(reopened)
    reopened.engine_commands = Queue()
    assert reopened.learning.achieved(1) and reopened.learning.lesson is None
    assert not reopened.start_pending and not reopened.guide_strip.isVisible()
    reopened.learning.begin(2)
    assert request(reopened)["parameters"]["fast"] == 10


def test_hiding_guidance_keeps_work_and_context_buttons_return_to_correct_account(window, qtbot):
    window.learning.begin(0)
    window.guide_strip.hide()
    assert window.learning.lesson == 0
    window.learning.run_id = "lessonaccount"
    window.active_id = "anotheraccount"
    window.learning.render()
    assert window.guide_next.text() == "返回练习账户"
    window.learning.act()
    assert window.active_id == "lessonaccount"
    assert window.engine_commands.get_nowait() == {"op": "load", "id": "lessonaccount"}
    window.switch_workspace(3)
    assert window.lesson_resume_guide.isVisible()
    qtbot.mouseClick(window.lesson_resume_guide, QtCore.Qt.MouseButton.LeftButton)
    assert window.guide_strip.isVisible()


def test_reading_mode_restores_panels_and_keeps_execution_controls_reachable(window):
    window.switch_workspace(3)
    window.library_dock.hide()
    window.parameter_dock.show()
    before = [dock.isVisible() for dock in (window.library_dock, window.parameter_dock, window.bottom_dock)]
    window.toggle_learning_layout()
    assert not any(dock.isVisible() for dock in (window.library_dock, window.parameter_dock, window.bottom_dock))
    assert not window.metrics_panel.isVisible()
    assert window.mode_badge.isVisible() and not window.start_button.isVisible()
    window.toggle_learning_layout()
    assert window.learning_layout is None
    assert [dock.isVisible() for dock in (window.library_dock, window.parameter_dock, window.bottom_dock)] == before
    window.toggle_learning_layout()
    window.switch_workspace(0)
    assert window.learning_layout is None and not window.metrics_panel.isVisible()
    assert window.editor.isVisible()
    assert not any(dock.isVisible() for dock in (window.library_dock, window.parameter_dock, window.bottom_dock))
    window.switch_workspace(2)
    assert window.metrics_panel.isVisible()
    assert window.trading_control_bar.isVisible()
    assert window.trading_tasks.create_button.isVisible()
    assert not window.library_dock.isVisible()
    assert all(dock.isVisible() for dock in (window.parameter_dock, window.bottom_dock))


def test_new_account_does_not_replace_lesson_evidence_and_early_stop_can_restart(window):
    window.learning.begin(0)
    window.learning.act()
    job = request(window)
    run = Run(job, window.root, Queue())
    try:
        display(window, run)
        another = {**run.message(), "id": "another"}
        window.learning.observe(another)
        assert window.learning.run_id == run.id
        request_without_tag = {key: value for key, value in job.items() if key != "learning"}
        window.learning.tag_request(request_without_tag)
        assert "learning" not in request_without_tag
        run.stop()
        display(window, run)
        old_attempt = window.learning.attempt
        assert window.guide_next.text() == "重新开始本节"
        window.learning.act()
        assert window.learning.attempt != old_attempt and window.learning.run_id is None
    finally:
        run.stop()


def test_preparing_next_lesson_clears_old_account_display_but_keeps_history(window):
    window.learning.begin(0)
    window.learning.act()
    run = Run(request(window), window.root, Queue())
    try:
        run.step()
        display(window, run)
        assert window.orders_table.model().rowCount() == 1 and window.stop_button.isEnabled()
        window.learning.begin(1)
        assert window.active_id is None and run.id in window.states
        assert "待创建" in window.account_status.text() and "待创建" in window.mode_badge.text()
        assert all(value.text() == "—" for value in window.metric_values.values())
        assert window.orders_table.model().rowCount() == 0 and not window.stop_button.isEnabled()
        assert run.broker.orders[0].active  # Only the selection changes, not that account's orders.
    finally:
        run.stop()
