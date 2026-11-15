"""Real public daily data + real dated states through the native editor and engine."""
from pathlib import Path
import time

from PySide6 import QtCore, QtWidgets
from shiboken6 import isValid

from astock.datasets import list_datasets
from astock.domain import dumps
from astock.rule_history_ui import RuleHistoryDialog


def start_status_smoke(application, window, screenshot):
    output = Path(screenshot).parent if screenshot else window.root / "reports/status-check"
    output.mkdir(parents=True, exist_ok=True)
    before = {m["id"] for m in list_datasets(window.root / "datasets")}
    timer = QtCore.QTimer(window)
    timer.setInterval(40)
    phase = "waiting"
    started = last = time.monotonic()
    maximum, original, meta, editor = 0.0, None, None, None
    original_bytes = None

    def finish(error="", state=None):
        timer.stop()
        report = {"passed": not error, "error": error, "source_is_real": True,
                  "state_source": "baostock", "price_source": "akshare-tencent",
                  "announcement": "https://static.cninfo.com.cn/finalpage/2024-06-25/1220444804.PDF",
                  "symbol": "600654.SH", "original": original, "metadata": meta,
                  "source_preserved": original is not None and original_bytes ==
                  (window.root / "datasets" / (original["id"] + ".json")).read_bytes(),
                  "timer_max_gap_ms": round(maximum*1000, 2), "device_pixel_ratio": window.devicePixelRatioF(),
                  "statistics": state["result"]["statistics"] if state else None,
                  "one_hour_market_acceptance": False}
        (output / "status-result.json").write_text(dumps(report), encoding="utf-8")
        window.grab().save(str(output / "status-backtest.png"))
        if editor and isValid(editor) and editor.isVisible():
            editor.reject()
        window.close()
        application.exit(2 if error else 0)

    def poll():
        nonlocal phase, last, maximum, original, original_bytes, meta, editor
        current = time.monotonic()
        maximum, last = max(maximum, current-last), current
        try:
            if current-started > 80:
                raise TimeoutError("真实历史状态下载及回测超时：" + phase)
            if phase == "waiting" and current-started > 1:
                phase = "configure"
                QtCore.QTimer.singleShot(0, window.download_dialog)
            elif phase == "configure":
                dialog = application.activeModalWidget()
                if dialog is None:
                    return
                dialog.findChild(QtWidgets.QLineEdit, "historySymbols").setText("600654.SH")
                combo = dialog.findChild(QtWidgets.QComboBox, "historyPeriod")
                combo.setCurrentIndex(combo.findData("1d"))
                for name, day in (("historyStart", 20), ("historyEnd", 28)):
                    dialog.findChild(QtWidgets.QDateEdit, name).setDate(QtCore.QDate(2024, 6, day))
                phase = "download"
                dialog.findChild(QtWidgets.QPushButton, "historyDownload").click()
            elif phase == "download":
                candidates = [m for m in list_datasets(window.root / "datasets") if m["id"] not in before
                              and m["id"] == window.dataset_combo.currentData() and m["source"] == "akshare-tencent"]
                if not candidates:
                    if window.history_process and not window.history_process.is_alive() and window.notice.isVisible():
                        raise AssertionError(window.notice.text())
                    return
                original = candidates[0]
                assert not original["demo"] and original["corporate_actions_verified"], original["notes"]
                original_bytes = (window.root / "datasets" / (original["id"] + ".json")).read_bytes()
                phase = "editor"
                QtCore.QTimer.singleShot(0, lambda: window.open_rule_history(original["id"]))
            elif phase == "editor":
                editor = application.activeModalWidget()
                if not isinstance(editor, RuleHistoryDialog):
                    return
                editor.symbols.setCurrentText("600654.SH")
                editor.fetch_button.click()
                phase = "preview"
            elif phase == "preview":
                if editor.token is None and not editor.preview:
                    raise AssertionError(editor.note.text())
                if not editor.preview or not editor.preview.isVisible():
                    return
                editor.preview.grab().save(str(output / "status-preview.png"))
                editor.preview.findChild(QtWidgets.QPushButton, "applyStockStatus").click()
                periods = editor.collect()["600654.SH"].history
                assert [(p.start, p.end, p.status) for p in periods] == [
                    ("2024-06-20", "2024-06-24", "risk_warning"),
                    ("2024-06-25", "2024-06-25", "suspended"),
                    ("2024-06-26", "2024-06-28", "normal")]
                editor.grab().save(str(output / "status-editor.png"))
                editor.save_button.click()
                phase = "saved"
            elif phase == "saved":
                candidates = [m for m in list_datasets(window.root / "datasets")
                              if m.get("parent_dataset", {}).get("id") == original["id"]
                              and m["id"] == window.dataset_combo.currentData()]
                if not candidates:
                    if isValid(editor) and editor.isVisible() and editor.token is None:
                        raise AssertionError(editor.note.text())
                    return
                meta = candidates[0]
                assert meta["sha256"] == original["sha256"]
                assert meta["rule_evidence"]["600654.SH"]["applied_without_edits"]
                window.mode_combo.setCurrentIndex(window.mode_combo.findData("backtest"))
                window.editor.setPlainText("""from astock.strategy import Strategy
class UserStrategy(Strategy):
    def on_bar(self, ctx, bar):
        if (bar.time.date().isoformat() >= '2024-06-26'
                and not ctx.position(bar.symbol)['quantity'] and not ctx.has_open_orders(bar.symbol)):
            ctx.order(bar.symbol, 'BUY', 100, ctx.limit_price(bar.symbol, float(bar.close)*1.01),
                      reason='历史状态验收；撤销ST后按下一日行情撮合')
""")
                window.speed_combo.setCurrentIndex(window.speed_combo.findData(1000))
                window.start_run()
                phase = "run"
            elif phase == "run":
                state = window.states.get(window.active_id)
                if state and state["status"] == "ERROR":
                    raise AssertionError(str(state.get("logs", [])))
                if state and state["status"] == "COMPLETED":
                    assert len(state["snapshot"]["trades"]) >= 1
                    assert all(t.time.date().isoformat() >= "2024-06-27" for t in state["snapshot"]["trades"])
                    finish(state=state)
        except Exception as error:
            finish(str(error))
    timer.timeout.connect(poll)
    timer.start()
    return timer
