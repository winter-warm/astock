"""Native/frozen UI exercise, with explicitly synthetic recording inputs."""
from datetime import datetime, timedelta
from pathlib import Path
import time

from PySide6 import QtCore, QtTest, QtWidgets

from astock.datasets import Recorder
from astock.domain import CN, Quote, dec, dumps, loads


def start_operations_smoke(application, window, screenshot=None):
    output = Path(screenshot).parent if screenshot else window.root / "reports/operations-check"
    output.mkdir(parents=True, exist_ok=True)
    recorders = [Recorder(window.root / "datasets") for _ in range(2)]
    at = datetime(2026, 11, 13, 10, tzinfo=CN)
    for recorder in recorders:
        recorder.append([Quote("600000.SH", at + timedelta(seconds=i), at + timedelta(seconds=i),
                               dec(10), dec(10), dec(10), 10000, 10000, 10000 + i * 100,
                               dec(10), dec(11), dec(9), source="synthetic-acceptance") for i in range(100)])
    recorders[0].seal()
    timer = QtCore.QTimer(application)
    state = {"phase": "run", "started": time.perf_counter(), "dialog": None, "last": None,
             "report": None, "comparison_rows": 0, "recovery": None}
    gaps = []

    def finish(error=""):
        timer.stop()
        recorders[1].seal()
        result = {"passed": not error, "error": error, "recording_fixture_is_synthetic": True,
                  "timer_max_gap_ms": round(max(gaps, default=0) * 1000, 2),
                  "device_pixel_ratio": window.devicePixelRatioF(), "exported_report": state["report"],
                  "comparison_rows": state["comparison_rows"], "recovery": state["recovery"]}
        (output / "operations-result.json").write_text(dumps(result), encoding="utf-8")
        window.close()
        application.exit(2 if error else 0)

    def click(text):
        action = next(b for b in window.findChildren(QtWidgets.QPushButton) if b.text() == text)
        QtTest.QTest.mouseClick(action, QtCore.Qt.MouseButton.LeftButton)

    def capture(dialog, name):
        dialog.layout().activate()
        available = dialog.screen().availableGeometry()
        assert dialog.frameGeometry().width() <= available.width(), "操作窗口超出屏幕宽度"
        assert dialog.frameGeometry().height() <= available.height(), "操作窗口超出屏幕高度"
        for widget in (dialog.summary, dialog.open_button, dialog.cancel_button, dialog.detail):
            assert dialog.rect().contains(QtCore.QRect(widget.mapTo(dialog, QtCore.QPoint()), widget.size())), "操作或说明裁切"
        assert dialog.detail.height() >= dialog.detail.heightForWidth(dialog.detail.width()), "详情文字裁切"
        dialog.grab().save(str(output / (name + ".png")))

    def poll():
        now = time.perf_counter()
        if state["last"]:
            gaps.append(now - state["last"])
            state["last"] = now
        try:
            if now - state["started"] > 55:
                raise AssertionError("后台操作验收超时")
            if state["phase"] == "run" and now - state["started"] > 1:
                window._select_demo("bar")
                window.speed_combo.setCurrentIndex(window.speed_combo.findData(1000))
                window.start_run()
                state["phase"] = "running"
            elif state["phase"] == "running":
                run = window.states.get(window.active_id)
                if not run or run["status"] != "COMPLETED":
                    return
                assert run["snapshot"]["trades"], "回测没有成交"
                state.update({"identity": run["id"], "trades": len(run["snapshot"]["trades"]), "last": now})
                click("导出报告")
                state["dialog"] = window.operations[("report", run["id"])]
                window.switch_workspace(3)
                state["phase"] = "report"
            elif state["phase"] == "report":
                dialog = state["dialog"]
                if dialog.token:
                    return
                assert dialog.report_path, dialog.summary.text()
                exported = loads(dialog.report_path.with_name("run.json").read_text(encoding="utf-8"))
                assert exported["id"] == state["identity"] and len(exported["snapshot"]["trades"]) == state["trades"]
                state["report"] = str(dialog.report_path)
                capture(dialog, "report")
                dialog.close()
                window.switch_workspace(1)
                click("运行对比")
                state["dialog"] = window.operations[("compare", None)]
                state["phase"] = "compare"
            elif state["phase"] == "compare":
                dialog = state["dialog"]
                if dialog.token:
                    return
                assert dialog.result, dialog.summary.text()
                rows = dialog.result["rows"]
                selected = next(i for i, row in enumerate(rows) if row["id"] == state["identity"])
                dialog.table.selectRow(selected)
                assert dialog.open_button.isEnabled()
                state["comparison_rows"] = len(rows)
                capture(dialog, "compare")
                QtTest.QTest.mouseClick(dialog.open_button, QtCore.Qt.MouseButton.LeftButton)
                assert window.active_id == state["identity"]
                dialog.close()
                window.recover_recordings()
                state["dialog"] = window.operations[("recover", None)]
                state["dialog"].setWindowTitle("整理录制行情 · 合成验收输入")
                state["phase"] = "recover"
            elif state["phase"] == "recover":
                dialog = state["dialog"]
                if dialog.token:
                    return
                assert dialog.result, dialog.summary.text()
                assert dialog.result["completed"] >= 1 and dialog.result["busy"] == 1, dialog.result
                state["recovery"] = dialog.result
                row = next(i for i, value in enumerate(dialog.result["rows"]) if value["status"] == "已完成")
                dialog.table.selectRow(row)
                capture(dialog, "recover")
                QtTest.QTest.mouseClick(dialog.open_button, QtCore.Qt.MouseButton.LeftButton)
                assert window.dataset_combo.currentData() == dialog.result["rows"][row]["dataset"]
                assert window.mode_combo.currentData() == "replay"
                finish()
        except Exception as error:
            finish(str(error))
    timer.timeout.connect(poll)
    timer.start(20)
    return timer
