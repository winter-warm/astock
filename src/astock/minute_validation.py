"""Native UI download from the real public source, followed by a real engine run."""
from datetime import timedelta
from pathlib import Path
import time

from PySide6 import QtCore, QtTest, QtWidgets

from astock.datasets import list_datasets
from astock.domain import dumps, now_cn
from astock.minute_history import previous_trading_day
from astock.trading_calendar import trading_day


def start_minute_smoke(application, window, screenshot):
    output = Path(screenshot).parent if screenshot else window.root / "reports" / "minute-check"
    output.mkdir(parents=True, exist_ok=True)
    before = {m["id"] for m in list_datasets(window.root / "datasets")}
    symbols = ["600000.SH", "000001.SZ", "510300.SH", "159915.SZ"]
    end = now_cn().date() - timedelta(days=1)
    while trading_day(end) is False:
        end -= timedelta(days=1)
    start = previous_trading_day(end)
    if start is None:
        raise ValueError("分钟验收日期尚无交易日历支持")
    timer = QtCore.QTimer(window)
    timer.setInterval(40)
    phase = "waiting"
    started = last = time.monotonic()
    maximum = 0.0
    meta = None

    def finish(error="", state=None):
        timer.stop()
        report = {"passed": not error, "error": error, "source_is_real": True, "source": "akshare-sina",
                  "symbols": symbols, "period": "1m", "request": {"start": str(start), "end": str(end)},
                  "timer_max_gap_ms": round(maximum*1000, 2), "device_pixel_ratio": window.devicePixelRatioF(),
                  "metadata": meta, "statistics": state["result"]["statistics"] if state else None,
                  "one_hour_market_acceptance": False}
        (output / "minute-result.json").write_text(dumps(report), encoding="utf-8")
        window.grab().save(str(output / "minute-backtest.png"))
        window.close()
        application.exit(2 if error else 0)

    def poll():
        nonlocal phase, last, maximum, meta
        current = time.monotonic()
        maximum = max(maximum, current-last)
        last = current
        try:
            if current-started > 55:
                raise TimeoutError("实际分钟下载或回测超时")
            if phase == "waiting" and current-started > 1:
                phase = "configure"
                QtCore.QTimer.singleShot(0, window.download_dialog)
            elif phase == "configure":
                dialog = application.activeModalWidget()
                if dialog is None:
                    return
                dialog.findChild(QtWidgets.QLineEdit, "historySymbols").setText(",".join(symbols))
                combo = dialog.findChild(QtWidgets.QComboBox, "historyPeriod")
                combo.setCurrentIndex(combo.findData("1m"))
                source = dialog.findChild(QtWidgets.QComboBox, "historySource")
                assert source.currentData() == "sina"
                dialog.findChild(QtWidgets.QDateEdit, "historyStart").setDate(QtCore.QDate(start.year, start.month, start.day))
                dialog.findChild(QtWidgets.QDateEdit, "historyEnd").setDate(QtCore.QDate(end.year, end.month, end.day))
                dialog.grab().save(str(output / "minute-download.png"))
                phase = "download"
                action = dialog.findChild(QtWidgets.QPushButton, "historyDownload")
                QtTest.QTest.mouseClick(action, QtCore.Qt.MouseButton.LeftButton, pos=action.rect().center())
            elif phase == "download":
                # Metadata is written last; the GUI must also have received history_done.
                identity = window.dataset_combo.currentData()
                candidates = [m for m in list_datasets(window.root / "datasets") if m["id"] not in before
                              and m["source"] == "akshare-sina" and m["id"] == identity]
                if not candidates:
                    if window.history_process and window.history_process.exitcode not in (None, 0):
                        raise AssertionError(window.notice.text() or "下载进程失败")
                    if window.history_process and not window.history_process.is_alive() and window.notice.isVisible():
                        raise AssertionError(window.notice.text())
                    return
                meta = candidates[0]
                assert meta["corporate_actions_verified"], meta["notes"]
                assert set(meta["symbols"]) == set(symbols)
                assert meta["period"] == "1m" and not meta["demo"]
                assert all(meta["provenance"][s]["references"] for s in symbols)
                window.mode_combo.setCurrentIndex(window.mode_combo.findData("backtest"))
                window.editor.setPlainText("""from astock.strategy import Strategy
class UserStrategy(Strategy):
    def on_bar(self, ctx, bar):
        if not ctx.position(bar.symbol)['quantity'] and not ctx.has_open_orders(bar.symbol):
            ctx.order(bar.symbol, 'BUY', 100, ctx.limit_price(bar.symbol, float(bar.close)*1.005),
                      reason='分钟来源验收；真实行情、虚拟资金')
""")
                window.speed_combo.setCurrentIndex(window.speed_combo.findData(1000))
                window.start_run()
                phase = "run"
            elif phase == "run":
                state = window.states.get(window.active_id)
                if state and state["status"] == "ERROR":
                    raise AssertionError(str(state.get("logs", [])))
                if state and state["status"] == "COMPLETED":
                    assert {t.symbol for t in state["snapshot"]["trades"]} == set(symbols)
                    finish(state=state)
        except Exception as error:
            finish(str(error))
    timer.timeout.connect(poll)
    timer.start()
    return timer
