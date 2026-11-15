"""Exercise the data-center button, background check, explanation row and report."""
from datetime import datetime
import json
from pathlib import Path
import time

from PySide6 import QtCore, QtTest, QtWidgets

from astock.datasets import list_datasets, write_dataset
from astock.domain import Bar, CN, dec
from astock.quality_ui import QualityDialog


def start_quality_smoke(application, window, screenshot=None, identity=None):
    output = Path(screenshot).parent if screenshot else window.root / "reports" / "quality-check"
    output.mkdir(parents=True, exist_ok=True)
    fixture = identity is None
    if fixture:
        events = []
        for at in ("11:29", "11:30", "13:01", "13:03", "14:57", "15:00"):
            events.append(Bar("600000.SH", datetime.fromisoformat("2026-11-13T" + at).replace(tzinfo=CN),
                              dec(10), dec(10), dec(10), dec(10), 10000, "1m", prev_close=dec(10), suspended=at == "14:57"))
        meta = write_dataset(window.root / "datasets", "教学 · 识别分钟缺口与停牌标记", events, demo=True,
                             source="synthetic-quality-acceptance", verified=True,
                             notes="人工构造的缺口检查练习，不是真实历史行情。")
        identity = meta["id"]
    else:
        assert any(m["id"] == identity for m in list_datasets(window.root / "datasets")), "指定数据不存在"
    timer = QtCore.QTimer(application)
    started = time.perf_counter()
    state = {"step": "center", "last": started, "dialog": None}
    gaps = []

    def finish(error=""):
        timer.stop()
        dialog = state["dialog"]
        result = {"passed": not error, "error": error, "fixture_is_synthetic": fixture,
                  "timer_max_gap_ms": round(max(gaps, default=0) * 1000, 2), "dataset_id": identity}
        if dialog:
            result.update({"device_pixel_ratio": dialog.devicePixelRatioF(), "summary": dialog.summary.text(),
                           "explanation": dialog.detail.text(), "row_count": dialog.table.model().rowCount(),
                           "report": str(dialog.report_path), "quality": dialog.report})
            dialog.grab().save(str(screenshot or output / "quality.png"))
            dialog.close()
        (output / "quality-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        window.close()
        application.exit(2 if error else 0)

    def poll():
        now = time.perf_counter()
        gaps.append(now - state["last"])
        state["last"] = now
        try:
            if now - started > 50:
                raise AssertionError("数据检查窗口验收超时")
            if state["step"] == "center":
                center = next((w for w in window.findChildren(QtWidgets.QDialog) if w.isVisible()
                               and w.windowTitle().startswith("数据中心")), None)
                if not center:
                    return
                table = center.findChild(QtWidgets.QTableWidget)
                row = next(i for i in range(table.rowCount()) if table.item(i, 0).data(QtCore.Qt.ItemDataRole.UserRole) == identity)
                table.selectRow(row)
                action = next(b for b in center.findChildren(QtWidgets.QPushButton) if b.text() == "检查缺口")
                state["step"] = "checking"
                # Defer to avoid re-entering this timer while QDialog.exec runs.
                QtCore.QTimer.singleShot(0, lambda: QtTest.QTest.mouseClick(action, QtCore.Qt.MouseButton.LeftButton))
            elif state["step"] == "checking":
                dialog = next((w for w in window.findChildren(QualityDialog) if w.isVisible()), None)
                if not dialog:
                    return
                state["dialog"] = dialog
                if dialog.token:
                    return
                assert dialog.report is not None, dialog.summary.text()
                assert dialog.open_button.isEnabled() and dialog.report_path.is_file(), "检查报告未保存"
                report = dialog.report
                assert dialog.table.model().rowCount() == len(report["details"])
                if fixture:
                    assert report["counts"]["missing_bars_total"] == 114
                    assert report["counts"]["suspended"] == report["counts"]["outside_session"] == 1
                    index = next(i for i, r in enumerate(report["details"]) if r["kind"] == "missing_bar")
                    dialog.table.selectRow(index)
                    assert "漏数" in dialog.detail.text()
                available = dialog.screen().availableGeometry()
                assert dialog.frameGeometry().height() <= available.height(), "窗口超出屏幕高度"
                for widget in (dialog.summary, dialog.cancel_button, dialog.open_button, dialog.detail):
                    rect = QtCore.QRect(widget.mapTo(dialog, QtCore.QPoint()), widget.size())
                    assert dialog.rect().contains(rect), "检查操作或说明被裁切"
                state["step"] = "capture"
                state["capture_after"] = now + 0.4
            elif state["step"] == "capture" and now >= state["capture_after"]:
                finish()
        except Exception as error:
            finish(str(error))
    timer.timeout.connect(poll)
    timer.start(20)
    QtCore.QTimer.singleShot(400, window.open_data_center)
    return timer
