from PySide6 import QtCore, QtWidgets
from astock.help_controller import HelpController
from astock.help_registry import help_entries, help_target, resolve_target


class Host(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.bar = QtWidgets.QStatusBar(self)

    def statusBar(self):
        return self.bar


def test_spinbox_editor_maps_to_registered_parent(qtbot):
    widget = help_target(QtWidgets.QSpinBox(), 'window.MainWindow._build_parameters.capital')
    qtbot.addWidget(widget)
    internal = widget.findChild(QtWidgets.QLineEdit)
    target, entry = resolve_target(internal)
    assert target is widget
    assert entry['reviewed']


def test_point_help_consumes_business_click(qtbot):
    host = Host()
    qtbot.addWidget(host)
    layout = QtWidgets.QVBoxLayout(host)
    button = help_target(QtWidgets.QPushButton('开始运行'), 'window.MainWindow._build_main.start_button')
    layout.addWidget(button)
    triggered = []
    button.clicked.connect(lambda: triggered.append(True))
    controller = HelpController(host)
    host.show()
    controller.pick()
    qtbot.mouseClick(button, QtCore.Qt.MouseButton.LeftButton)
    assert triggered == []
    assert controller.dialog.isVisible()
    assert not controller.picking
    controller.close()


def test_all_registered_entries_have_explanation():
    assert len(help_entries()) >= 200
    for identity, entry in help_entries().items():
        assert entry['reviewed'], identity
        assert entry['title'] and entry['explanation'] and entry['steps'] and entry['unavailable'], identity


def test_disabled_control_can_be_explained_without_changing_state(qtbot):
    host = Host()
    qtbot.addWidget(host)
    layout = QtWidgets.QVBoxLayout(host)
    button = help_target(QtWidgets.QPushButton('运行练习'), 'course_ui.CourseLibrary.__init__.run_button')
    button.setEnabled(False)
    layout.addWidget(button)
    controller = HelpController(host)
    host.show()
    controller.pick()
    qtbot.mouseClick(button, QtCore.Qt.MouseButton.LeftButton)
    assert controller.dialog is not None and controller.dialog.isVisible()
    assert not button.isEnabled()
    controller.close()


def test_reopen_help_after_parent_dialog_is_destroyed(qtbot):
    from shiboken6 import isValid
    host = Host()
    qtbot.addWidget(host)
    controller = HelpController(host)
    parent = QtWidgets.QDialog(host)
    button = help_target(QtWidgets.QPushButton('测试', parent), 'course_ui.CourseLibrary.__init__.run_button')
    parent.show()
    controller.explain(button)
    previous = controller.dialog
    parent.close()
    parent.deleteLater()
    qtbot.waitUntil(lambda: not isValid(previous))
    controller.close()  # Application shutdown also tolerates the destroyed child.
    target = help_target(QtWidgets.QPushButton('另一个控件', host), 'course_ui.CourseLibrary.__init__.run_button')
    assert controller.explain(target)
    assert isValid(controller.dialog)
    controller.close()


def test_disabled_menu_action_explanation_uses_action_state(qtbot):
    host = Host()
    qtbot.addWidget(host)
    menu = QtWidgets.QMenu(host)
    action = help_target(menu.addAction('暂停'), 'window.MainWindow._build_main.pause_action')
    action.setEnabled(False)
    menu.setActiveAction(action)
    controller = HelpController(host)
    assert controller.explain(menu, action=action)
    browser = controller.dialog.findChild(QtWidgets.QTextBrowser)
    assert '不可操作' in browser.toPlainText()
    assert controller.dialog.parentWidget() is host
    controller.close()
