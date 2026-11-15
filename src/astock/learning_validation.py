"""Click the four-course path through real GUI, engine and strategy processes."""
from pathlib import Path
import time

from PySide6 import QtCore, QtTest

from astock.domain import dumps


def start_learning_smoke(application, window, screenshot=None, online=False):
    output = Path(screenshot).parent if screenshot else window.root / "reports/learning-check"
    output.mkdir(parents=True, exist_ok=True)
    timer = QtCore.QTimer(application)
    started = time.perf_counter()
    state = {"phase": "start", "last": started, "after": started + 1, "observations": [], "online": None}
    gaps = []

    def click(widget):
        window.centralWidget().layout().activate()
        window.pages.currentWidget().layout().activate()
        if window.workspace_scroll.isAncestorOf(widget):
            window.workspace_scroll.ensureWidgetVisible(widget)
        assert widget.isEnabled(), f"按钮未启用：{widget.text()}"
        assert widget.visibleRegion().contains(widget.rect().center()), f"按钮中心不可见：{widget.text()}"
        QtTest.QTest.mouseClick(widget, QtCore.Qt.MouseButton.LeftButton)

    def course(index):
        click(window.nav_group.button(3))
        # Historical regression route; old practice has no public navigation tab.
        window.learning_sections.setCurrentIndex(0)
        window.workspace_scroll.verticalScrollBar().setValue(0)
        click(window.lesson_buttons[index])
        if window.learning_layout is None:
            click(window.lesson_reading)

    def capture(name):
        window.centralWidget().layout().activate()
        window.grab().save(str(output / (name + ".png")))
        assert window.guide_strip.isVisible()
        assert window.guide_next.visibleRegion().contains(window.guide_next.rect().center()), "练习操作被裁切"
        assert window.guide_text.height() >= window.guide_text.heightForWidth(window.guide_text.width()), "练习说明被裁切"

    def observe(name):
        run = window.learning.last_state
        state["observations"].append({"step": name, "run": run["id"] if run else None,
            "mode": run["mode"] if run else None, "status": run["status"] if run else None,
            "orders": len(run["snapshot"]["orders"]) if run else 0,
            "trades": len(run["snapshot"]["trades"]) if run else 0,
            "frozen": str(run.get("frozen", 0)) if run else "0", "guide": window.guide_text.text()})

    def finish(error=""):
        timer.stop()
        result = {"passed": not error, "error": error, "course_count": sum(window.learning.achieved(i) for i in range(4)),
                  "practice_records": window.learning.records, "observations": state["observations"],
                  "offline_synthetic": True, "online_requested": online, "online_result": state["online"],
                  "device_pixel_ratio": window.devicePixelRatioF(), "window": [window.width(), window.height()],
                  "timer_max_gap_ms": round(max(gaps, default=0) * 1000, 2),
                  "one_hour_market_acceptance": False}
        (output / "learning-result.json").write_text(dumps(result), encoding="utf-8")
        window.close()
        application.exit(2 if error else 0)

    def next_phase(phase, delay=.25):
        state["phase"], state["after"] = phase, time.perf_counter() + delay

    def select_trade():
        table = window.trades_table
        index = table.model().index(0, 0)
        table.scrollTo(index)
        rectangle = table.visualRect(index)
        assert table.viewport().rect().contains(rectangle.center()), "成交行不可见"
        QtTest.QTest.mouseClick(table.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=rectangle.center())

    def poll():
        now = time.perf_counter()
        gaps.append(now - state["last"])
        state["last"] = now
        try:
            if now - started > (85 if online else 55):
                raise AssertionError("四课验收超时：" + state["phase"])
            if now < state["after"]:
                return
            phase = state["phase"]
            run = window.learning.last_state
            if run and run["status"] == "ERROR":
                raise AssertionError("练习引擎异常：" + window.log_view.toPlainText()[-1000:])
            if phase == "start":
                course(0)
                click(window.lesson_action)
                next_phase("first_step")
            elif phase == "first_step":
                click(window.guide_next)
                next_phase("order")
            elif phase == "order" and run and run["result"]["index"] == 1:
                assert not run["snapshot"]["trades"] and run["snapshot"]["orders"][0].active
                assert run["status"] == "PAUSED"
                observe("first_quote_pending")
                capture("01-order")
                click(window.guide_next)
                next_phase("filled")
            elif phase == "filled" and run and run["snapshot"]["trades"]:
                observe("second_quote_filled")
                click(window.guide_next)
                next_phase("first_trade")
            elif phase == "first_trade":
                select_trade()
                next_phase("first_complete")
            elif phase == "first_complete" and window.learning.complete(0):
                capture("01-trade")
                course(1)
                click(window.lesson_action)
                next_phase("parameters")
            elif phase == "parameters":
                assert window.active_id is None and "待创建" in window.account_status.text()
                assert not window.stop_button.isEnabled() and window.orders_table.model().rowCount() == 0
                click(window.guide_next)
                widget = window.parameters["fast"]
                widget.selectAll()
                QtTest.QTest.keyClicks(widget, "10")
                QtTest.QTest.keyClick(widget, QtCore.Qt.Key.Key_Tab)
                assert widget.value() == 10
                click(window.guide_next)
                assert window.learning.complete(1)
                capture("02-parameters")
                course(2)
                click(window.lesson_action)
                next_phase("backtest")
            elif phase == "backtest" and run and run["status"] == "COMPLETED":
                assert run["manifest"]["parameters"]["fast"] == 10
                assert run["snapshot"]["trades"]
                observe("backtest_finished_with_changed_parameters")
                click(window.guide_next)
                next_phase("metrics")
            elif phase == "metrics":
                assert "metrics" in window.learning.steps(2)
                capture("03-metrics")
                click(window.guide_next)
                next_phase("backtest_trade")
            elif phase == "backtest_trade":
                select_trade()
                next_phase("backtest_complete")
            elif phase == "backtest_complete" and window.learning.complete(2):
                assert window.trade_context["points"]
                capture("03-trade")
                course(3)
                click(window.lesson_offline)
                next_phase("offline_start")
            elif phase == "offline_start":
                click(window.guide_next)
                next_phase("offline_order")
            elif phase == "offline_order" and run and run["result"]["index"] == 1:
                assert len(run["snapshot"]["orders"]) == 2 and not run["snapshot"]["trades"]
                click(window.guide_next)
                next_phase("offline_fill")
            elif phase == "offline_fill" and run and run["snapshot"]["trades"]:
                assert sum(order.active for order in run["snapshot"]["orders"]) == 1 and run["frozen"] > 0
                click(window.guide_next)
                next_phase("offline_stopped")
            elif phase == "offline_stopped" and run and run["status"] == "STOPPED":
                assert not any(order.active for order in run["snapshot"]["orders"]) and run["frozen"] == 0
                assert all(window.learning.achieved(i) for i in range(4))
                assert not window.connected and not window.quotes
                observe("offline_stopped_and_released")
                capture("04-offline-stopped")
                course(3)
                next_phase("course_complete")
            elif phase == "course_complete":
                capture("04-course-complete")
                if online:
                    click(window.lesson_action)
                    next_phase("online_connect")
                else:
                    finish()
            elif phase == "online_connect":
                click(window.guide_next)
                next_phase("online_quotes")
            elif phase == "online_quotes" and "quote" in window.learning.steps(3):
                assert window.quotes
                state["online"] = {"sources": sorted({quote.source for quote in window.quotes.values()}),
                                   "quotes": list(window.quotes.values()), "status": window.market_status.text()}
                click(window.guide_next)
                next_phase("online_account")
            elif phase == "online_account" and run and run["mode"] == "live":
                assert run["status"] == "RUNNING" and "account" in window.learning.steps(3)
                observe("online_account_started")
                capture("04-online-account")
                click(window.guide_next)
                next_phase("online_stop")
            elif phase == "online_stop" and run and run["status"] == "STOPPED":
                assert window.learning.complete(3)
                state["online"]["run_id"] = run["id"]
                state["online"]["stopped"] = True
                capture("04-online-stopped")
                finish()
        except Exception as error:
            finish(str(error))
    timer.timeout.connect(poll)
    timer.start(30)
    return timer
