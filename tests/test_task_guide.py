from PySide6 import QtCore, QtWidgets
from astock.help_registry import help_entries, help_target
from astock.task_guide import TaskGuide, paths


def test_all_task_steps_have_real_stable_targets():
    registry = help_entries()
    for task in paths():
        assert len(task['steps']) >= 4
        for step in task['steps']:
            assert step['target'] in registry
            assert all(step.get(key) for key in ('route', 'instruction', 'expect'))


def test_task_navigation_never_activates_business_controls(qtbot):
    window = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(window)
    first = paths()[0]['steps'][0]
    button = help_target(QtWidgets.QPushButton('业务动作'), first['target'])
    layout.addWidget(button)
    calls = []
    button.clicked.connect(lambda: calls.append(True))
    qtbot.addWidget(window)
    window.show()
    guide = TaskGuide(window)
    guide.show()
    assert guide.band is not None
    guide.next.click()
    guide.previous.click()
    assert calls == []
    qtbot.keyClick(guide, QtCore.Qt.Key.Key_Escape)
    assert not guide.timer.isActive() and guide.band is None
