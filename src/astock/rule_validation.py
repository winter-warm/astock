"""Native GUI acceptance of sourced rule revision and an engine run."""
from datetime import datetime
from pathlib import Path
import time

from PySide6 import QtCore, QtTest

from astock.datasets import write_dataset
from astock.domain import Bar, CN, dec, dumps
from astock.rule_history_ui import RuleHistoryDialog


def start_rule_smoke(application, window, screenshot):
    output = Path(screenshot).parent if screenshot else window.root / "reports" / "rules"
    output.mkdir(parents=True, exist_ok=True)
    events = [Bar("600000.SH", datetime(2026, 7, d, 15, tzinfo=CN), dec(10), dec("10.1"),
                  dec("9.9"), dec(10), 1000000, prev_close=dec(10)) for d in (2, 3, 6, 7)]
    meta = write_dataset(window.root / "datasets", "教学 · ST 生效日期边界", events,
                         source="astock-rule-boundary-v1", demo=True, verified=True)
    original = (window.root / "datasets" / (meta["id"] + ".json")).read_bytes()
    dialog = RuleHistoryDialog(window.root, meta["id"], window)
    screen = window.screen().availableGeometry()
    dialog.resize(min(window.width(), screen.width() - 40), min(590, screen.height() - 60))
    dialog.show()
    timer = QtCore.QTimer(window)
    timer.setInterval(40)
    started = last = time.monotonic()
    maximum = 0.0
    phase = 0

    def click(widget):
        if not widget.isVisible() or not widget.isEnabled():
            raise AssertionError("操作按钮不可见或不可用")
        QtTest.QTest.mouseClick(widget, QtCore.Qt.MouseButton.LeftButton, pos=widget.rect().center())

    def finish(passed, error="", state=None):
        timer.stop()
        result = {"passed": passed, "error": error, "fixture_is_synthetic": True,
                  "timer_max_gap_ms": round(maximum * 1000, 2), "device_pixel_ratio": window.devicePixelRatioF(),
                  "window": [window.width(), window.height()], "revised_id": dialog.saved_id,
                  "source_preserved": (window.root / "datasets" / (meta["id"] + ".json")).read_bytes() == original,
                  "statistics": state["result"]["statistics"] if state else None,
                  "orders": state["snapshot"]["orders"] if state else [],
                  "rule_engine": state["manifest"].get("rule_engine") if state else None}
        (output / "rules-result.json").write_text(dumps(result), encoding="utf-8")
        dialog.close()
        window.close()
        application.exit(0 if passed else 2)

    def poll():
        nonlocal phase, last, maximum
        current = time.monotonic()
        maximum = max(maximum, current - last)
        last = current
        try:
            if current - started > 35:
                raise TimeoutError("规则修订或回测未在时限内结束")
            if phase == 0 and current - started > .5:
                click(dialog.add_button)
                click(dialog.save_button)
                assert "来源" in dialog.note.text()
                dialog.grid.item(0, 6).setText("人工构造的 ST 状态；只验收操作及生效日期，不是真实股票历史")
                combo = dialog.grid.cellWidget(0, 3)
                combo.setCurrentIndex(combo.findData("risk_warning"))
                phase = 1
            elif phase == 1:
                dialog.grab().save(str(output / "rules-editor.png"))
                click(dialog.save_button)
                phase = 2
            elif phase == 2 and dialog.saved_id:
                window.refresh_library()
                window.dataset_combo.setCurrentIndex(window.dataset_combo.findData(dialog.saved_id))
                window.mode_combo.setCurrentIndex(window.mode_combo.findData("backtest"))
                window.editor.setPlainText("""from astock.strategy import Strategy
class UserStrategy(Strategy):
    def on_bar(self, ctx, bar):
        ctx.order(bar.symbol, 'BUY', 100, 10.6, reason='检查当日风险警示涨跌幅')
""")
                window.speed_combo.setCurrentIndex(window.speed_combo.findData(1000))
                window.start_run()
                phase = 3
            elif phase == 3:
                state = window.states.get(window.active_id)
                if not state and not window.start_pending and window.notice.isVisible():
                    raise AssertionError(window.notice.text())
                if state and state["status"] == "ERROR":
                    raise AssertionError(str(state.get("logs", [])))
                if state and state["status"] == "COMPLETED":
                    orders = state["snapshot"]["orders"]
                    assert [o.status for o in orders[:3]] == ["REJECTED", "FILLED", "FILLED"]
                    assert state["snapshot"]["trades"][0].time.day == 6
                    assert state["manifest"]["rules"]["600000.SH"].history
                    window.grab().save(str(output / "rules-backtest.png"))
                    finish(True, state=state)
        except Exception as error:
            finish(False, str(error))
    timer.timeout.connect(poll)
    timer.start()
    return timer
