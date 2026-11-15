"""After-hours UI integration probe. Uses only local virtual orders."""
import multiprocessing as mp
from pathlib import Path
import sys
import time


def main():
    import argparse
    from PySide6 import QtCore, QtWidgets
    from astock.domain import dumps
    from astock.window import MainWindow
    app = QtWidgets.QApplication([])
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="output/live-ui-qa")
    args = parser.parse_args()
    out = Path(args.output_dir).resolve()
    root = out / "data"
    window = MainWindow(root)
    window.resize(1280, 760)
    window.show()
    start = time.monotonic()
    stages = set()
    out.mkdir(parents=True, exist_ok=True)
    def tick():
        elapsed = time.monotonic() - start
        if "start" not in stages and elapsed > 1:
            stages.add("start")
            window.record_check.setChecked(True)
            window.start_live(True)
        state = window.states.get(window.active_id)
        if len(window.quotes) == 4 and state and "order" not in stages:
            stages.add("order")
            window.use_opposite_price()
            window.manual_order()
        if elapsed > 12 and "stop_record" not in stages:
            stages.add("stop_record")
            window.record_check.setChecked(False)
        recorded = [x for x in window.datasets if x["source"] == "tencent-recording"]
        if state and recorded and elapsed > 14 and "stop_account" not in stages:
            stages.add("stop_account")
            window.send_run("stop")
        if state and state["status"] == "STOPPED" and "finish" not in stages:
            stages.add("finish")
            window.switch_workspace(2)
            window.bottom_tabs.setCurrentIndex(1)
            window.grab().save(str(out / "live.png"))
            result = {"quotes": len(window.quotes), "recordings": len(recorded),
                      "orders": state["snapshot"]["orders"], "trades": state["snapshot"]["trades"],
                      "input_archive": state["manifest"].get("input_archive"),
                      "dataset": state["manifest"].get("dataset"),
                      "one_hour_market_acceptance": False,
                      "status": state["status"], "processes_alive": all(p.is_alive() for p in window.processes)}
            (out / "result.json").write_text(dumps(result), encoding="utf-8")
            window.close()
            app.exit(0 if result["quotes"] == 4 and result["orders"] else 2)
        elif elapsed > 35:
            (out / "failure.txt").write_text(window.log_view.toPlainText() + "\n" + window.market_status.text(), encoding="utf-8")
            window.close()
            app.exit(3)
    timer = QtCore.QTimer()
    timer.timeout.connect(tick)
    timer.start(200)
    sys.exit(app.exec())


if __name__ == "__main__":
    mp.freeze_support()
    main()
