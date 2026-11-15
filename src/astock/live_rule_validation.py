"""Real-source native account flow; after-hours observations are not market acceptance."""
from pathlib import Path
import time

from PySide6 import QtCore, QtTest

from astock.domain import dumps, now_cn
from astock.rules import rule_at


def start_live_rule_smoke(application, window, screenshot=None):
    output = Path(screenshot).parent if screenshot else window.root / "reports/live-rules-check"
    output.mkdir(parents=True, exist_ok=True)
    started = last = time.monotonic()
    maximum, phase = 0, "start"
    timer = QtCore.QTimer(application)
    account_id = None

    def click(widget):
        window.centralWidget().layout().activate()
        window.pages.currentWidget().layout().activate()
        if window.workspace_scroll and window.workspace_scroll.isAncestorOf(widget):
            window.workspace_scroll.ensureWidgetVisible(widget)
        assert widget.isVisible() and widget.isEnabled(), "操作按钮不可用"
        assert widget.visibleRegion().contains(widget.rect().center()), "操作按钮被遮挡"
        QtTest.QTest.mouseClick(widget, QtCore.Qt.MouseButton.LeftButton)

    def finish(error=""):
        timer.stop()
        state = window.states.get(account_id)
        report = {"passed": not error, "error": error, "phase": phase,
                  "source_is_real": bool(state and state["manifest"].get("live_rule_observations")), "account": state,
                  "device_pixel_ratio": window.devicePixelRatioF(),
                  "timer_max_gap_ms": round(maximum * 1000, 2), "one_hour_market_acceptance": False}
        (output / "live-rules-result.json").write_text(dumps(report), encoding="utf-8")
        window.grab().save(str(output / "live-rules.png"))
        window.close()
        application.exit(2 if error else 0)

    def poll():
        nonlocal phase, last, maximum, account_id
        current = time.monotonic()
        maximum, last = max(maximum, current - last), current
        try:
            if current - started > 110:
                raise TimeoutError("当日 ETF 规则账户验收超时：" + phase + "；" + window.live_rule_status.text())
            state = window.states.get(account_id)
            if phase == "start" and current - started > .8:
                window.switch_workspace(2)
                window.symbol_input.setText("158000.SZ,158011.SZ,551300.SH")
                click(window.create_manual_button)
                assert window.start_pending
                phase = "creating"
            elif phase == "creating" and window.active_id and not window.start_pending:
                account_id = window.active_id
                state = window.states.get(account_id)
                if not state:
                    return
                assert state["mode"] == "manual" and state["status"] == "RUNNING"
                rules = state["manifest"]["rules"]
                day = now_cn().date().isoformat()
                assert rule_at(rules["158000.SZ"], day).t_plus == 0
                assert rule_at(rules["551300.SH"], day).t_plus == 0
                assert float(rule_at(rules["158011.SZ"], day).limit_rate) == .2
                assert state["manifest"]["live_rule_observations"][-1]["valid_day"] == day
                assert not state["snapshot"]["trades"]
                window.grab().save(str(output / "live-rules-created.png"))
                window.pause_action.trigger()
                phase = "pausing"
            elif phase == "pausing" and state and state["status"] == "PAUSED":
                click(window.refresh_live_rule_button)
                phase = "refreshing"
            elif phase == "refreshing" and state and not window.live_rule_token:
                if not any("当日规则已更新" in item["message"] for item in state["result"]["logs"]):
                    return
                assert state["status"] == "PAUSED" and state["snapshot"]["account"].cash == 100000
                window.resume_action.trigger()
                phase = "resuming"
            elif phase == "resuming" and state and state["status"] == "RUNNING":
                click(window.stop_button)
                phase = "stopping"
            elif phase == "stopping" and state and state["status"] == "STOPPED":
                assert state["frozen"] == 0 and not state["snapshot"]["trades"]
                finish()
        except Exception as error:
            finish(str(error))
    timer.timeout.connect(poll)
    timer.start(40)
    return timer
