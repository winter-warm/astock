from PySide6 import QtCore, QtWidgets

from astock.model_trading import TradingTasks
from astock.window import MainWindow


def test_tasks_only_list_live_accounts_and_refresh_keeps_identity(qtbot, tmp_path):
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    for identity, mode in (("live-one", "live"), ("manual-two", "manual"), ("historical", "backtest")):
        window.store.save_run(identity, identity, mode, "STOPPED", {}, {}, {})
    tasks = TradingTasks(window)
    qtbot.addWidget(tasks)
    assert tasks.accounts.rowCount() == 2
    first = tasks.accounts.item(0, 0).data(QtCore.Qt.ItemDataRole.UserRole)
    tasks.accounts.selectRow(0)
    assert window.active_id is None
    window.states[first] = {"name": first, "mode": "live", "status": "PAUSED"}
    window.store.save_run("newest", "newest", "live", "RUNNING", {}, {}, {})
    tasks.refresh()
    assert tasks.selected_id() == first
    assert tasks.accounts.item(tasks.accounts.currentRow(), 3).text() == "已暂停"
    tasks.view_account()
    assert window.active_id == first
    assert window.pages.currentIndex() == 2
    assert window.engine_commands.get(timeout=2) == {"op": "load", "id": first}
    window.close()


def test_new_task_preserves_current_source_and_uses_existing_start_path(qtbot, tmp_path, monkeypatch):
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.show()
    original_name = window.current_template
    window.editor.appendPlainText("# unsaved trading experiment")
    original_code = window.editor.toPlainText()
    starts = []
    monkeypatch.setattr(window, "start_live", lambda manual: starts.append(
        (manual, window.current_template, window.symbol_input.text(), window.capital.value())))
    tasks = TradingTasks(window)
    qtbot.addWidget(tasks)
    errors = []

    def fill():
        dialog = QtWidgets.QApplication.activeModalWidget()
        try:
            symbols = dialog.findChild(QtWidgets.QLineEdit, "tradingTaskSymbols")
            symbols.setText("600000.SH，000001.SZ，600000.SH")
            capital = dialog.findChild(QtWidgets.QDoubleSpinBox, "tradingTaskCapital")
            capital.setValue(250000)
            buttons = dialog.findChild(QtWidgets.QDialogButtonBox)
            buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).click()
        except Exception as exc:
            errors.append(exc)
            dialog.reject()

    QtCore.QTimer.singleShot(50, fill)
    tasks.new_task()
    assert not errors, errors
    assert starts == [(False, original_name, "600000.SH,000001.SZ", 250000)]
    assert window.editor.toPlainText() == original_code
    assert next(s["code"] for s in window.store.strategies() if s["name"] == original_name) == original_code
    window.close()


def test_invalid_symbols_or_cancel_do_not_start_or_replace_model(qtbot, tmp_path, monkeypatch):
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    window.show()
    code = window.editor.toPlainText()
    starts = []
    monkeypatch.setattr(window, "start_live", lambda manual: starts.append(manual))
    tasks = TradingTasks(window)
    qtbot.addWidget(tasks)
    errors = []

    def reject_invalid():
        dialog = QtWidgets.QApplication.activeModalWidget()
        try:
            dialog.findChild(QtWidgets.QLineEdit, "tradingTaskSymbols").clear()
            dialog.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.StandardButton.Ok).click()
            assert dialog.isVisible()
            assert "1–20" in dialog.findChild(QtWidgets.QLabel, "tradingTaskError").text()
        except Exception as exc:
            errors.append(exc)
        finally:
            dialog.reject()

    QtCore.QTimer.singleShot(50, reject_invalid)
    tasks.new_task()
    assert not errors, errors
    assert starts == []
    assert window.editor.toPlainText() == code
    window.close()
