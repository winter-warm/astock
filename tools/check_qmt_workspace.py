"""Native desktop captures with a real offline backtest; no market connection."""
from pathlib import Path
from queue import Queue
import multiprocessing as mp

from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from astock.engine import Run
from astock.window import MainWindow


def main():
    root = Path(__file__).resolve().parents[1] / "output" / "qmt-workspace-qa"
    root.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication([])
    app.setFont(QtGui.QFont("Microsoft YaHei UI", 9))
    window = MainWindow(root / "data", start_workers=False)
    window.fit_initial_layout(1280, 800)
    window.reset_layout()
    window.show()

    def capture(name):
        QtTest.QTest.qWait(200)
        window.grab().save(str(root / (name + ".png")))

    window.switch_workspace(4)
    capture("home")
    window.switch_workspace(0)
    capture("research")
    window.open_strategy_editor()
    QtTest.QTest.qWait(250)
    window.strategy_dialog.grab().save(str(root / "editor.png"))
    window.strategy_dialog.close()
    run = Run({"mode": "backtest", "dataset": window.dataset_combo.currentData(),
               "code": window.editor.toPlainText(), "parameters": window.parameter_values(),
               "initial": 100000}, root / "data", Queue())
    try:
        while run.status == "RUNNING":
            run.step()
        assert run.status == "COMPLETED"
        state = run.message()
        window.states[run.id] = state
        window.active_id = run.id
        window.display_run(state)
        window.switch_workspace(4)
        window.home_accounts.refresh()
        window.home_accounts.selector.setCurrentIndex(window.home_accounts.selector.findData(run.id))
        capture("accounts")
        window.home_accounts.tabs.setCurrentIndex(1)
        capture("account-operations")
        window.switch_workspace(1)
        capture("backtest")
        window.toggle_analysis_layout()
        window.result_tabs.setCurrentWidget(window.diagnostics)
        capture("diagnostics")
        from astock.reports import export_report
        export_report(root, state)
        window.switch_workspace(3)
        window.learning_sections.setCurrentIndex(1)
        capture("migration")
        window.fit_initial_layout(1024, 680)
        capture("migration-small")
        window.switch_workspace(1)
        capture("diagnostics-small")
        assert window.nav_group.button(1).visibleRegion().contains(window.nav_group.button(1).rect().center())
        QtCore.QTimer.singleShot(0, window.close)
        QtCore.QTimer.singleShot(100, app.quit)
        app.exec()
    finally:
        if run.host:
            run.host.close()
        window.close()


if __name__ == "__main__":
    mp.freeze_support()
    main()
