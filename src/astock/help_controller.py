"""F1 and point-to-explain work in the active window, including modal dialogs."""
from astock.help_registry import help_target
from PySide6 import QtCore, QtWidgets
from shiboken6 import isValid

from astock.help_registry import describe, resolve_target, runtime_details


class HelpController(QtCore.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.picking = False
        self.consume_release = False
        self.dialog = None
        QtWidgets.QApplication.instance().installEventFilter(self)

    def pick(self):
        if not self.picking:
            self.picking = True
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WhatsThisCursor)
            self.window.statusBar().showMessage('点选要解释的控件，不会执行原动作；Esc 退出。')

    def stop_pick(self):
        if self.picking:
            self.picking = False
            QtWidgets.QApplication.restoreOverrideCursor()
            self.window.statusBar().clearMessage()

    def explain(self, widget, *, action=None):
        target, entry = (widget, describe(action)) if action is not None else resolve_target(widget)
        if target is None or not entry:
            return False
        owner = target
        while isinstance(owner, QtWidgets.QMenu) and owner.parentWidget():
            owner = owner.parentWidget()
        parent = owner.window()
        dialog = QtWidgets.QDialog(parent)
        dialog.setWindowTitle('控件说明')
        dialog.resize(560, 340)
        layout = QtWidgets.QVBoxLayout(dialog)
        title = entry.get('title') or entry.get('label') or target.accessibleName() or '当前控件'
        text = help_target(QtWidgets.QTextBrowser(), 'help_controller.HelpController.explain.text')
        details = [title, entry['explanation'], entry.get('steps', ''), entry.get('unavailable', '')]
        details.append(runtime_details(target))
        control = action or (target.activeAction() if isinstance(target, QtWidgets.QMenu) and target.activeAction() else target)
        if control.toolTip():
            details.append('此控件当前提示：' + control.toolTip())
        details.append('当前状态：' + ('可操作' if control.isEnabled() else '不可操作，请核对前置条件'))
        text.setPlainText('\n\n'.join(x for x in details if x))
        layout.addWidget(text)
        actions = help_target(QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close), 'help_controller.HelpController.explain.actions')
        actions.rejected.connect(dialog.reject)
        layout.addWidget(actions)
        if self.dialog is not None and isValid(self.dialog):
            self.dialog.close()
            self.dialog.deleteLater()
        self.dialog = dialog
        dialog.show()
        return True

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() == QtCore.Qt.Key.Key_F1:
                if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
                    self.window.explain_current_page()
                elif event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                    self.pick()
                else:
                    self.explain(QtWidgets.QApplication.focusWidget())
                return True
            if event.key() == QtCore.Qt.Key.Key_Escape and self.picking:
                self.stop_pick()
                return True
        if self.picking and event.type() == QtCore.QEvent.Type.MouseButtonPress:
            self.stop_pick()
            self.consume_release = True
            action = watched.actionAt(event.position().toPoint()) if isinstance(watched, QtWidgets.QMenu) else None
            self.explain(watched, action=action)
            return True
        if self.consume_release and event.type() == QtCore.QEvent.Type.MouseButtonRelease:
            self.consume_release = False
            return True
        return super().eventFilter(watched, event)

    def close(self):
        self.stop_pick()
        QtWidgets.QApplication.instance().removeEventFilter(self)
        if self.dialog is not None and isValid(self.dialog):
            self.dialog.close()
