"""Exercise tutorial ownership and side effects through the actual application window."""

import pytest
from PySide6 import QtCore, QtWidgets
from shiboken6 import isValid

from astock.data_jobs import DataJobs
from astock.help_registry import help_target
from astock.window import MainWindow


@pytest.fixture
def tutorial_window(qtbot, tmp_path, monkeypatch):
    jobs = []

    def record_start(self, kind, **request):
        jobs.append((kind, request))
        return f"isolated-job-{len(jobs)}"

    # MainWindow requests a chart preview even with engine/market workers disabled.
    # Keep the real UI and DataJobs objects, but isolate all subprocess starts.
    monkeypatch.setattr(DataJobs, "start", record_start)
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)
    jobs.clear()
    yield window, jobs
    if isValid(window):
        window.close()


def dialog_control(window):
    dialog = QtWidgets.QDialog(window)
    layout = QtWidgets.QVBoxLayout(dialog)
    target = help_target(
        QtWidgets.QPushButton("开始运行"), "window.MainWindow._build_main.start_button"
    )
    layout.addWidget(target)
    dialog.show()
    dialog.activateWindow()
    target.setFocus()
    return dialog, target


def destroy_dialog(dialog):
    dialog.close()
    dialog.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    assert not isValid(dialog)


@pytest.mark.parametrize("next_action", ["reopen", "close"])
def test_destroyed_parent_tour_supports_next_help_and_shutdown(tutorial_window, qtbot, next_action):
    window, _ = tutorial_window
    dialog, target = dialog_control(window)
    qtbot.waitUntil(lambda: QtWidgets.QApplication.activeWindow() is dialog)
    qtbot.keyClick(target, QtCore.Qt.Key.Key_F1, QtCore.Qt.KeyboardModifier.ControlModifier)
    previous = window.control_tour
    assert previous.parentWidget() is dialog
    assert previous.timer.isActive()

    destroy_dialog(dialog)
    assert not isValid(previous)
    if next_action == "reopen":
        window.activateWindow()
        qtbot.waitUntil(lambda: QtWidgets.QApplication.activeWindow() is window)
        window.explain_current_page()
        assert isValid(window.control_tour)
        assert window.control_tour is not previous
        assert window.control_tour.parentWidget() is window
        assert window.control_tour.timer.isActive()

    window.close()
    assert window.closing
    if next_action == "reopen":
        assert not window.control_tour.timer.isActive()


def test_destroyed_parent_point_help_can_be_replaced(tutorial_window):
    window, _ = tutorial_window
    dialog, target = dialog_control(window)
    assert window.help_controller.explain(target)
    previous = window.help_controller.dialog
    assert previous.parentWidget() is dialog
    destroy_dialog(dialog)
    assert not isValid(previous)
    assert window.help_controller.explain(window.start_button)
    assert isValid(window.help_controller.dialog)
    assert window.help_controller.dialog is not previous
    window.close()
    assert not window.help_controller.dialog.isVisible()


@pytest.mark.parametrize("kind", ["quality", "report", "compare", "recover"])
def test_main_window_instruction_preview_never_starts_jobs(tutorial_window, kind):
    window, jobs = tutorial_window
    before = set(window.root.rglob("*"))
    dialog = window.open_instruction_preview(kind)
    tour = dialog._instruction_tour
    assert dialog.instruction_preview
    assert dialog.isVisible() and tour.isVisible()
    assert tour.timer.isActive()
    assert not dialog.retry.isEnabled()
    assert not dialog.open_button.isEnabled()
    # Even a previously queued start callback must respect preview mode.
    dialog.start()
    assert jobs == []
    assert not dialog.jobs.active
    dialog.close()
    assert not tour.timer.isActive()
    assert tour.band is None
    assert not tour.isVisible()
    assert not dialog.jobs.timer.isActive()
    assert jobs == []
    assert set(window.root.rglob("*")) == before


def test_task_navigation_preserves_unsaved_model_without_business_actions(
    tutorial_window, monkeypatch
):
    window, jobs = tutorial_window
    window.editor.appendPlainText("# 未保存草稿：任务引导不得保存或改写")
    draft = window.editor.toPlainText()
    saved = window.store.strategies()
    calls = []

    def record_save(*args, **kwargs):
        calls.append("save_strategy")

    def record_start(*args, **kwargs):
        calls.append("start_run")

    # Restore these methods before normal application shutdown, which does save.
    with monkeypatch.context() as patches:
        patches.setattr(window, "save_strategy", record_save)
        patches.setattr(window, "start_run", record_start)
        window.open_task_guide()
        guide = window.task_guide
        for task_index, task in enumerate(guide.tasks):
            guide.selector.setCurrentIndex(task_index)
            assert guide.index == 0
            for index in range(1, len(task["steps"])):
                guide.next.click()
                assert guide.index == index
                assert window.editor.toPlainText() == draft
            for index in reversed(range(len(task["steps"]) - 1)):
                guide.previous.click()
                assert guide.index == index
        guide.close()
        assert not guide.timer.isActive() and guide.band is None
        assert calls == []
        assert jobs == []
        assert window.editor.toPlainText() == draft
        assert window.store.strategies() == saved


def test_first_run_tour_targets_visible_and_never_saves_or_starts(tutorial_window, monkeypatch):
    from astock.onboarding import open_onboarding, STEPS

    window, jobs = tutorial_window
    window.editor.appendPlainText('# 我的未保存草稿')
    draft = window.editor.toPlainText()
    calls = []
    with monkeypatch.context() as patches:
        patches.setattr(window, 'save_strategy', lambda *a, **k: calls.append('save'))
        patches.setattr(window, 'start_run', lambda *a, **k: calls.append('run'))
        tour = open_onboarding(window)
        for index in range(len(STEPS)):
            assert tour.index == index
            assert tour.target is not None and tour.target.isVisible(), STEPS[index]
            assert tour.band.isVisible()
            assert window.editor.toPlainText() == draft
            tour.advance(1)
        assert not tour.isVisible() and not tour.timer.isActive()
        assert window.editor.isVisible()
        assert not calls and not jobs


@pytest.mark.parametrize('initial_debug', [False, True])
def test_tour_chapters_reveal_controls_and_restore_debug_view(tutorial_window, initial_debug):
    from astock.onboarding import open_onboarding, STEPS

    window, jobs = tutorial_window
    window.backtest_controls_toggle.setChecked(initial_debug)
    saved = window.store.strategies()
    tour = open_onboarding(window, start_chapter='回测运行')
    assert tour.chapter.currentText() == '回测运行'
    assert tour.target is window.backtest_start_button
    for chapter in ('写策略', '回测准备', '读取结果', '模拟交易', '记录与课程'):
        tour.choose_chapter(tour.chapter.findText(chapter))
        assert tour.chapter.currentText() == chapter
        assert tour.target.isVisible() and tour.band.isVisible()
        assert tour.expected.text().startswith('核对：')
    tour.index = next(i for i, step in enumerate(STEPS) if step[2] == 'run_toolbar')
    tour.render()
    assert window.run_toolbar.isVisible()
    tour.close()
    assert window.backtest_controls_toggle.isChecked() is initial_debug
    assert window.store.strategies() == saved
    assert not jobs
