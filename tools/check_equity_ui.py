"""Native Qt exercise: use the tutorial button and real engine single stepping."""
import argparse
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys
import time


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "windows")
    from PySide6 import QtCore, QtWidgets
    from astock.window import MainWindow
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication([])
    app.setApplicationName("AStock")
    app.setOrganizationName("AStock")
    window = MainWindow(output / "data")
    window.fit_initial_layout(1280, 760)
    window.show()
    window.show_lesson(2)
    window.switch_workspace(3)
    started = time.monotonic()
    observations = []
    phase, last_index, last_action = "prepare", 0, started
    error = None
    def finish():
        nonlocal error
        chart = window.result_chart
        viewport = window.workspace_scroll.viewport()
        top = chart.mapTo(viewport, QtCore.QPoint(0, 0)).y()
        if error is None and not (0 <= top and top + chart.height() <= viewport.height()):
            error = "选中成交后图表未完整出现在分析视野中"
        details = {"completed": error is None, "error": error, "steps": observations,
                   "device_pixel_ratio": window.devicePixelRatioF(),
                   "viewport_height": viewport.height(), "chart_top": top,
                   "chart_bottom": top + chart.height(), "chart_height": chart.height(),
                   "stack_minimum": window.pages.minimumSize().height(),
                   "stack_height": window.pages.height(),
                   "stack_height_for_width": window.pages.heightForWidth(window.pages.width()),
                   "stack_hint": window.pages.minimumSizeHint().height(),
                   "page_hint": window.pages.currentWidget().minimumSizeHint().height()}
        (output / "result.json").write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
        window.grab().save(str(output / "complete.png"))
        window.close()
        app.exit(0 if error is None else 1)
    def poll():
        nonlocal phase, last_index, last_action, error
        try:
            if time.monotonic() - started > 35:
                raise RuntimeError("教学单步流程超时")
            if phase == "prepare":
                window.equity_lesson_button.click()
                window.step_action.trigger()
                phase = "stepping"
                last_action = time.monotonic()
            elif phase == "stepping":
                state = window.states.get(window.active_id)
                if not state or state["result"]["index"] <= last_index:
                    return
                assert state["status"] in ("PAUSED", "COMPLETED"), state["status"]
                if time.monotonic() - last_action < .4:
                    return
                last_index = state["result"]["index"]
                snapshot = state["snapshot"]
                observations.append({"index": last_index, "status": state["status"],
                                     "cash": str(snapshot["account"].cash),
                                     "equity_rows": window.equity_table.model().rowCount(),
                                     "available": state["available_positions"],
                                     "note": window.equity_note.text()})
                if last_index == 3:
                    assert "应收分红 100.00" in window.equity_note.text()
                    assert state["available_positions"]["600000.SH"] == 100
                    window.grab().save(str(output / "receivable.png"))
                if state["status"] == "COMPLETED":
                    assert state["available_positions"]["600000.SH"] == 200
                    assert window.equity_table.model().rowCount() == 2
                    assert "累计到账 100.00" in window.equity_note.text()
                    window.trades_table.selectRow(0)
                    window.bottom_tabs.setCurrentIndex(4)
                    phase = "finishing"
                    timer.stop()
                    QtCore.QTimer.singleShot(600, finish)
                else:
                    window.step_action.trigger()
                    last_action = time.monotonic()
        except Exception as exc:
            error = str(exc)
            timer.stop()
            finish()
    timer = QtCore.QTimer()
    timer.timeout.connect(poll)
    timer.start(100)
    sys.exit(app.exec())


if __name__ == "__main__":
    mp.freeze_support()
    main()
